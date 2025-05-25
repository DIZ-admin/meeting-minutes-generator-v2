from typing import Dict, Tuple, Optional, List, Any
import os
import json
import jsonschema
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI, APIError
import tiktoken

# Constants for chunking transcripts
CHUNK_TOKENS = 550  # Approximately 2 pages of speech
OVERLAP = 100       # Token overlap between chunks

class OpenAIProcessor:
    """Handles interactions with the OpenAI API for text processing tasks."""
    def __init__(self, api_key: str = None, default_model: str = "gpt-4o"):
        """
        Initializes the OpenAIProcessor.

        Args:
            api_key: OpenAI API key. If None, it's fetched from OPENAI_API_KEY env var.
            default_model: The default OpenAI model to use (e.g., "gpt-4o").
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable or pass it directly.")
        self.client = OpenAI(api_key=self.api_key)
        self.default_model = default_model

    def _execute_chat_completion(self, messages: List[Dict], model: str, temperature: float, 
                                 response_format_type: str = "json_object", timeout: float = 90.0, 
                                 max_retries: int = 3) -> str:
        """
        Private helper method to execute a chat completion call with retry logic.

        Args:
            messages: A list of message dictionaries for the chat completion.
            model: The OpenAI model to use.
            temperature: Sampling temperature.
            response_format_type: Type of response format (e.g., "json_object").
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries for the API call.

        Returns:
            The content string from the LLM response.

        Raises:
            RuntimeError: If the API call fails after all retries.
        """
        last_exception = None
        retry_delay = 5 # seconds
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": response_format_type} if response_format_type else None,
                    temperature=temperature,
                    timeout=timeout
                )
                content = response.choices[0].message.content
                if content is None or content.strip() == "":
                    # Allow empty string if that's a valid model output, but log it.
                    # Consider raising an error if empty is always invalid for a specific call.
                    print(f"Warning: OpenAI API returned empty content for model {model} on attempt {attempt + 1}")
                    # For JSON, an empty string is invalid, so we might want to raise here
                    if response_format_type == "json_object": 
                         raise ValueError("OpenAI API returned empty content when JSON was expected.")
                    return "" # Or handle as error if empty is not acceptable
                return content
            except APIError as e:
                last_exception = e
                print(f"OpenAI API error (attempt {attempt+1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
            except Exception as e:
                last_exception = e
                print(f"Unexpected error during OpenAI call (attempt {attempt+1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2
        
        raise RuntimeError(f"Failed OpenAI API call after {max_retries} attempts: {last_exception}") from last_exception

    def map_segment(self, segment_text: str, model: str = None, temperature: float = 0.2) -> Dict:
        """
        Processes a single transcript segment (MAP stage).
        """
        model = model or self.default_model
        system_message = """
        You are a meeting secretary. Analyze this meeting segment and extract:
        1. A concise summary
        2. Any decisions made
        3. Any action items/tasks assigned
        
        Return a JSON with this structure:
        {
            "summary": "Brief summary of key points",
            "decisions": ["List of decisions made"],
            "actions": [
                {"who": "Person name", "what": "Task description", "due": "YYYY-MM-DD or null"}
            ]
        }
        """
        user_message = f"Meeting segment text:\n\n{segment_text}"
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        try:
            raw_json_response = self._execute_chat_completion(messages, model, temperature, response_format_type="json_object")
            result = json.loads(raw_json_response)
            # Ensure basic structure even if LLM omits keys
            result.setdefault("summary", "")
            result.setdefault("decisions", [])
            result.setdefault("actions", [])
            return result
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from map_segment: {e}. Response: {raw_json_response}")
            return {"summary": f"Error: Could not parse LLM JSON response. Details: {e}", "decisions": [], "actions": []}
        except RuntimeError as e:
            print(f"Error in map_segment after retries: {e}")
            return {"summary": f"Error processing segment: {e}", "decisions": [], "actions": []}

    def reduce_content(self, combined_text: str, model: str = None, temperature: float = 0.3) -> Dict:
        """
        Combines and deduplicates results from MAP stage (REDUCE stage).
        """
        model = model or self.default_model
        system_message = """
        Combine these meeting segment summaries, decisions, and actions into a unified list of decisions and actions.
        Remove or merge duplicates (similarity ≥ 80% for human understanding, be precise).
        Ensure the output maintains all unique decisions and actions.
        
        Input format will be a combined text of summaries, decisions, and actions from various segments.

        Output format should be a JSON object with these keys:
        {
            "decisions": ["List of unique decisions"],
            "actions": [
                {"who": "Person name", "what": "Task description", "due": "YYYY-MM-DD or null"}
            ]
        }
        """
        user_message = f"Combined meeting data:\n\n{combined_text}"
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
        try:
            raw_json_response = self._execute_chat_completion(messages, model, temperature, response_format_type="json_object")
            result = json.loads(raw_json_response)
            result.setdefault("decisions", [])
            result.setdefault("actions", [])
            return result
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from reduce_content: {e}. Response: {raw_json_response}")
            return {"decisions": [f"Error: Could not parse LLM JSON response. Details: {e}"], "actions": []}
        except RuntimeError as e:
            print(f"Error in reduce_content after retries: {e}")
            return {"decisions": [f"Error processing reduction: {e}"], "actions": []}

    def refine_to_protocol_json_str(self, refinement_prompt: str, model: str = None, temperature: float = 0.5) -> str:
        """
        Generates the final protocol JSON string based on a detailed prompt (REFINE stage).
        """
        model = model or self.default_model
        # The refinement_prompt is expected to be a fully formed user message.
        # The system message here can be minimal or guide the overall persona if needed.
        system_message = "You are an expert meeting secretary, tasked with producing a final, structured meeting protocol in JSON format according to the user's detailed instructions."
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": refinement_prompt} # refinement_prompt is the large user message
        ]
        try:
            # For refine, the output is a JSON string, but the response itself might not be a simple JSON object in structure,
            # it's the *content* of the message. So response_format_type might be None or 'text' if issues with 'json_object'.
            # However, the prompt itself asks for JSON, so 'json_object' should be fine.
            return self._execute_chat_completion(messages, model, temperature, response_format_type="json_object")
        except RuntimeError as e:
            print(f"Error in refine_to_protocol_json_str after retries: {e}")
            # Return a valid JSON string indicating error for graceful downstream failure
            error_json = {
                "error": "Failed to generate protocol due to LLM error",
                "details": str(e),
                "metadata": {},
                "agenda_items": [],
                "summary": "Protocol generation failed.",
                "decisions": [],
                "action_items": []
            }
            return json.dumps(error_json)

def split_transcript(transcript: Any, chunk_tokens: int = CHUNK_TOKENS, overlap: int = OVERLAP, encoding_name: str = "cl100k_base") -> List[str]:
    """
    Split transcript into chunks for processing using tokenization.
    
    Args:
        transcript: Transcript data (can be list of segments or nested JSON structure or plain text).
        chunk_tokens: Maximum tokens per chunk.
        overlap: Overlap tokens between chunks.
        encoding_name: The name of the tiktoken encoding to use (e.g., "cl100k_base").
        
    Returns:
        List of text chunks ready for processing.
    """
    texts = []
    
    if isinstance(transcript, str):
        texts.append(transcript)
    elif isinstance(transcript, dict):
        if "output" in transcript:
            if isinstance(transcript["output"], list):
                for segment in transcript["output"]:
                    if isinstance(segment, dict) and "text" in segment:
                        texts.append(segment["text"])
            elif isinstance(transcript["output"], dict) and "segments" in transcript["output"]:
                for segment in transcript["output"]["segments"]:
                    if isinstance(segment, dict) and "text" in segment:
                        texts.append(segment["text"])
    elif isinstance(transcript, list):
        for segment in transcript:
            if isinstance(segment, dict):
                text_content = segment.get("text", "")
                if text_content:
                    texts.append(text_content)
            elif isinstance(segment, str):
                texts.append(segment)
    
    if not texts:
        print(f"Warning: Could not extract any text from transcript of type {type(transcript)}")
        return ["No transcription text available"] # Return list with a single string
    
    full_text = " ".join(texts)
    
    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        print(f"Error getting tiktoken encoding {encoding_name}: {e}. Falling back to simple split.")
        # Fallback to simple character split if tiktoken fails (e.g., model not found)
        # This is a basic fallback, consider if a more robust one is needed.
        chunk_size_chars = chunk_tokens * 4  # Rough approximation
        # overlap_chars = overlap * 4 # Overlap chars not easily applicable here without token context
        return [full_text[i:i + chunk_size_chars] for i in range(0, len(full_text), chunk_size_chars)]

    all_tokens = encoding.encode(full_text)
    chunks = []
    start_token_idx = 0
    
    while start_token_idx < len(all_tokens):
        end_token_idx = min(start_token_idx + chunk_tokens, len(all_tokens))
        
        # Get the token slice for the current chunk
        current_chunk_tokens = all_tokens[start_token_idx:end_token_idx]
        
        # Decode the tokens back to text
        chunk_text = encoding.decode(current_chunk_tokens)
        chunks.append(chunk_text)
        
        # Determine the start of the next chunk
        if end_token_idx >= len(all_tokens):
            break # Reached the end of the transcript
        
        # Move start_token_idx forward, considering overlap
        # Ensure overlap doesn't cause an infinite loop or go out of bounds
        start_token_idx += chunk_tokens - overlap
        if start_token_idx >= end_token_idx : # prevent infinite loop if overlap >= chunk_tokens
             start_token_idx = end_token_idx # move to the next non-overlapping segment

    if not chunks: # Handle empty full_text case after tokenization, though unlikely if `texts` had content
        return ["No processable text after tokenization"]
        
    return chunks

def map_call(segment: str, processor: OpenAIProcessor = None) -> Dict:
    """
    Process a single transcript segment to extract summary, decisions, and actions.
    Now uses OpenAIProcessor.
    Args:
        segment: Text segment to process
        processor: Optional instance of OpenAIProcessor. If None, a new one is created.
        
    Returns:
        Dictionary with summary, decisions, and actions
    """
    local_processor = processor or OpenAIProcessor()
    return local_processor.map_segment(segment_text=segment)

def reduce_results(map_outputs: List[Dict], processor: OpenAIProcessor = None) -> Dict:
    """
    Combine and deduplicate the results from the MAP stage.
    Now uses OpenAIProcessor.
    
    Args:
        map_outputs: List of individual segment outputs
        processor: Optional instance of OpenAIProcessor. If None, a new one is created.
        
    Returns:
        Consolidated dictionary of decisions and action items
    """
    local_processor = processor or OpenAIProcessor()
    
    # Construct the combined text for the REDUCE operation (logic from original function)
    combined_summaries = "\n\n".join([
        str(item.get('summary', '')) for item in map_outputs 
        if item.get('summary') and str(item.get('summary', '')).strip()
    ])
    all_decisions = []
    all_actions = []
    for item in map_outputs:
        all_decisions.extend(item.get('decisions', []))
        all_actions.extend(item.get('actions', []))
    
    # Basic deduplication before sending to LLM (can be improved)
    unique_decisions = sorted(list(set(d for d in all_decisions if isinstance(d, str) and d.strip())))
    # Deduplicate actions based on 'what' field, could be more sophisticated
    seen_actions_what = set()
    unique_actions = []
    for action in all_actions:
        if isinstance(action, dict) and action.get('what'):
            if action['what'] not in seen_actions_what:
                unique_actions.append(action)
                seen_actions_what.add(action['what'])

    # Prepare the text input for the LLM reduce call
    reduce_input_text = f"Combined Summaries:\n{combined_summaries}\n\nExtracted Decisions (pre-deduplication):\n{json.dumps(all_decisions, indent=2)}\n\nExtracted Actions (pre-deduplication):\n{json.dumps(all_actions, indent=2)}"
    
    # Call the processor's reduce method
    return local_processor.reduce_content(combined_text=reduce_input_text)

    # Nächste Sitzung
    naechste_sitzung_json = current_protocol_json.get('naechste_sitzung')
    if naechste_sitzung_json and any(naechste_sitzung_json.values()):
        md_parts.append("## Nächste Sitzung")
        md_parts.append(f"- **Datum:** {naechste_sitzung_json.get('datum', 'N/A')}")
        md_parts.append(f"- **Zeit:** {naechste_sitzung_json.get('zeit', 'N/A')}")
        md_parts.append(f"- **Ort:** {naechste_sitzung_json.get('ort', 'N/A')}")
        md_parts.append("")
    
    markdown_text = "\n".join(md_parts)
    return markdown_text, current_protocol_json

def refine_to_protocol(reduced_data: Dict, transcript_info: Dict, processor: OpenAIProcessor = None, schema_path: str = None) -> Tuple[str, Dict]:
    """
    Generate the final meeting minutes in both Markdown and JSON formats.
    Now uses OpenAIProcessor for the LLM call.
    
    Args:
        reduced_data: Consolidated decisions and actions from reduce_results.
        transcript_info: Additional meeting info (date, participants, etc.).
        processor: Optional instance of OpenAIProcessor. If None, a new one is created.
        schema_path: Optional path to the JSON schema for validation.
        
    Returns:
        Tuple of (markdown_text, json_data)
    """
    local_processor = processor or OpenAIProcessor()

    # --- Logic for building the refinement_prompt (from original function) ---
    meeting_date = transcript_info.get('date', 'N/A')
    meeting_title = transcript_info.get('title', 'Meeting Protocol')
    participants = transcript_info.get('participants', [])
    agenda = transcript_info.get('agenda', []) # Expected to be a list of strings

    # Ensure decisions and actions are lists
    decisions = reduced_data.get('decisions', [])
    if not isinstance(decisions, list):
        decisions = [str(decisions)] if decisions else []
    
    actions = reduced_data.get('actions', [])
    if not isinstance(actions, list):
        actions = [actions] if actions else [] # Should be list of dicts, handle if not

    # Prepare participant list for prompt
    present_participants_list = []
    if isinstance(participants, dict):
        present_participants_list = participants.get('present', [])
    elif isinstance(participants, list):
        present_participants_list = participants # Assume it's already a list of participant dicts

    participant_list_str = "\n".join([f"- {p.get('name', 'Unknown')} ({p.get('role', 'Participant')})" for p in present_participants_list])
    if not participant_list_str:
        participant_list_str = "- (No participants listed)"

    # Prepare agenda list for prompt
    agenda_list_str = "\n".join([f"{i+1}. {item}" for i, item in enumerate(agenda)])
    if not agenda_list_str:
        agenda_list_str = "- (No agenda items listed)"

    # Prepare decisions list for prompt
    decisions_list_str = "\n".join([f"- {d}" for d in decisions])
    if not decisions_list_str:
        decisions_list_str = "- (No decisions recorded)"

    # Prepare action items list for prompt
    action_items_list_str = "\n".join([
        f"- Task: {a.get('what', 'N/A')}, Assigned to: {a.get('who', 'N/A')}, Due: {a.get('due', 'N/A')}"
        for a in actions
    ])
    if not action_items_list_str:
        action_items_list_str = "- (No action items recorded)"

    refinement_prompt = f"""
    Generate a formal meeting protocol in JSON format based on the following information.
    The JSON should adhere to the provided schema structure (implicitly, as it's complex to put full schema here).
    Focus on clarity, completeness, and formal tone.

    Meeting Title: {meeting_title}
    Date: {meeting_date}

    Participants:
    {participant_list_str}

    Agenda:
    {agenda_list_str}

    Key Decisions Made:
    {decisions_list_str}

    Action Items:
    {action_items_list_str}

    Please generate a JSON object with the following main keys:
    - "metadata": {{ "title": "...", "date": "...", "location": "..." (if known, else N/A), "organizer": "..." (if known, else N/A) }}
    - "participants": [ {{ "name": "...", "role": "...", "present": true/false (assume true if listed) }} ]
    - "agenda_items": [ {{ "topic": "...", "discussion_summary": "Brief summary of discussion on this topic (can be generated/inferred if not directly provided).", "decisions_made": ["relevant decision 1", ...], "action_items_assigned": [{{ "who": "...", "what": "...", "due": "..." }}] }} ]
       (Try to associate decisions and actions with agenda items if possible, otherwise list them globally)
    - "summary": "Overall concise summary of the meeting's main outcomes and discussions."
    - "decisions": [ {{ "decision_id": "D001", "description": "..." }} ] (global decisions not tied to a specific agenda item)
    - "action_items": [ {{ "action_id": "A001", "assigned_to": "...", "description": "...", "due_date": "...", "status": "Open" }} ] (global actions)
    
    Important considerations for JSON content:
    - For 'agenda_items', if discussion summaries are not explicitly provided, generate plausible brief summaries based on the agenda topic and any related decisions/actions.
    - If decisions or actions can be linked to specific agenda items, list them under that agenda item's "decisions_made" or "action_items_assigned" arrays. Otherwise, list them in the global "decisions" and "action_items" arrays.
    - Ensure all provided decisions and actions are included either globally or under an agenda item.
    - Provide unique IDs for decisions and action items (e.g., D001, A001).
    - Dates should be in YYYY-MM-DD format.
    """
    # --- End logic for building refinement_prompt ---

    raw_json_output_str = local_processor.refine_to_protocol_json_str(refinement_prompt)

    try:
        protocol_json_data = json.loads(raw_json_output_str)
    except json.JSONDecodeError as e_json:
        print(f"ERROR: Failed to parse LLM response as JSON: {e_json}. Raw output: '{raw_json_output_str}'")
        json_output = create_fallback_json_structure(transcript_info, reduced_data, str(e_json), raw_json_output_str)
        print(f"INFO: Created fallback JSON structure due to parsing error.")
        
        markdown_generated_for_fallback = False # Флаг, что markdown уже сгенерирован

        if schema_path:
            try:
                # Логика загрузки схемы, адаптированная из else блока
                if not os.path.isabs(schema_path):
                    current_script_dir = pathlib.Path(__file__).parent
                    schema_file_path = current_script_dir.parent / schema_path
                else:
                    schema_file_path = pathlib.Path(schema_path)

                if schema_file_path.exists():
                    with open(schema_file_path, 'r') as f_schema:
                        schema_data_for_fallback = json.load(f_schema)
                    
                    # Валидация fallback JSON (json_output)
                    jsonschema.validate(instance=json_output, schema=schema_data_for_fallback) # ИСПОЛЬЗУЕМ jsonschema.validate
                    
                    print(f"INFO: Fallback JSON structure passed schema validation.")
                    error_info_for_markdown = (
                        f"Initial JSON parsing from LLM failed: {e_json}. "
                        f"Using a fallback JSON structure that passed schema validation."
                    )
                    markdown_output = generate_markdown_error_protocol(
                        transcript_info, 
                        reduced_data, 
                        error_info_for_markdown, 
                        raw_json_output_str, 
                        json_output
                    )
                    markdown_generated_for_fallback = True
                else:
                    print(f"Warning: JSON schema file not found at {schema_file_path} for fallback validation. Skipping validation.")
                    # Генерируем markdown с предупреждением об отсутствии схемы
                    error_info_for_markdown = (
                        f"Initial JSON parsing from LLM failed: {e_json}. "
                        f"Fallback JSON was created, but schema file for its validation was not found at '{schema_file_path}'."
                    )
                    markdown_output = generate_markdown_error_protocol(
                        transcript_info, reduced_data, error_info_for_markdown, raw_json_output_str, json_output
                    )
                    markdown_generated_for_fallback = True

            except jsonschema.exceptions.ValidationError as e_schema_fallback:
                log_message = (
                    f"Fallback JSON failed schema validation after LLM JSON parsing failed. "
                    f"LLM error: {e_json}. Fallback schema validation error: {e_schema_fallback}"
                )
                print(f"ERROR: {log_message}")
                error_info_for_markdown = (
                    f"Initial JSON parsing from LLM failed: {e_json}. "
                    f"Subsequent schema validation for fallback JSON also failed: {e_schema_fallback}."
                )
                markdown_output = generate_markdown_error_protocol(
                    transcript_info, 
                    reduced_data, 
                    error_info_for_markdown, 
                    raw_json_output_str, 
                    json_output
                )
                raise ValueError(
                    f"Failed to parse LLM response as JSON, and fallback JSON schema validation failed with: {e_schema_fallback}"
                ) from e_schema_fallback
            except FileNotFoundError:
                print(f"Warning: Schema file '{schema_path}' not found during fallback validation.")
                error_info_for_markdown = (
                        f"Initial JSON parsing from LLM failed: {e_json}. "
                        f"Fallback JSON was created, but schema file for its validation ('{schema_path}') was not found."
                    )
                markdown_output = generate_markdown_error_protocol(
                        transcript_info, reduced_data, error_info_for_markdown, raw_json_output_str, json_output
                    )
                markdown_generated_for_fallback = True
            except Exception as e_val:
                 print(f"An error occurred during fallback JSON schema validation: {e_val}")
                 error_info_for_markdown = (
                        f"Initial JSON parsing from LLM failed: {e_json}. "
                        f"Fallback JSON was created, but an error occurred during its schema validation: {e_val}."
                    )
                 markdown_output = generate_markdown_error_protocol(
                        transcript_info, reduced_data, error_info_for_markdown, raw_json_output_str, json_output
                    )
                 markdown_generated_for_fallback = True # Считаем, что markdown сгенерирован с ошибкой
                 # Решаем, нужно ли здесь ValueError. Для теста - нет, если не хотим проверять этот конкретный Exception.
        else:
            print("Warning: schema_path not provided for fallback JSON validation. Skipping validation.")
            error_info_for_markdown = (
                f"Initial JSON parsing from LLM failed: {e_json}. "
                f"Fallback JSON was created, but no schema_path was provided for its validation."
            )
            markdown_output = generate_markdown_error_protocol(
                transcript_info, reduced_data, error_info_for_markdown, raw_json_output_str, json_output
            )
            markdown_generated_for_fallback = True
        
        # Если не было ValueError из-за e_schema_fallback, возвращаем markdown и json_output
        return markdown_output, json_output

    # Если не было исключений при парсинге и валидации JSON от LLM
    else:
        # --- JSON Schema Validation (from original function) ---
        if schema_path:
            try:
                # Determine absolute path for schema if relative
                if not os.path.isabs(schema_path):
                    # Assuming schema_path is relative to the project root or a known 'schema' directory
                    # For robustness, this might need adjustment based on actual project structure / execution context
                    current_script_dir = pathlib.Path(__file__).parent
                    schema_file_path = current_script_dir.parent / schema_path # e.g., ../schema/egl_protokoll.json
                else:
                    schema_file_path = pathlib.Path(schema_path)

                if schema_file_path.exists():
                    with open(schema_file_path, 'r') as f_schema:
                        schema = json.load(f_schema)
                    jsonschema.validate(instance=protocol_json_data, schema=schema)
                    print("Generated JSON protocol is valid against the schema.")
                else:
                    print(f"Warning: JSON schema file not found at {schema_file_path}. Skipping validation.")
            except jsonschema.exceptions.ValidationError as e_schema:
                print(f"Generated JSON protocol is INVALID against the schema: {e_schema.message}")
                # Optionally, include schema validation error in the output or raise an error
                protocol_json_data.setdefault("schema_validation_errors", []).append(e_schema.message)
            except FileNotFoundError:
                print(f"Warning: Schema file '{schema_path}' not found. Skipping JSON validation.")
            except Exception as e_val:
                print(f"An error occurred during JSON schema validation: {e_val}")
        # --- End JSON Schema Validation ---

        # --- Markdown Generation (from original function, adapted for new JSON structure if needed) ---
        md_parts = []
        md_parts.append(f"# Meeting Protocol: {protocol_json_data.get('metadata', {}).get('title', 'N/A')}")
        md_parts.append(f"**Date:** {protocol_json_data.get('metadata', {}).get('date', 'N/A')}")
        md_parts.append(f"**Location:** {protocol_json_data.get('metadata', {}).get('location', 'N/A')}")
        md_parts.append(f"**Organizer:** {protocol_json_data.get('metadata', {}).get('organizer', 'N/A')}")

        md_parts.append("## Participants")
        for p in protocol_json_data.get('participants', []):
            md_parts.append(f"- {p.get('name', 'Unknown')} ({p.get('role', 'Participant')})")
        if not protocol_json_data.get('participants'): md_parts.append("- None listed")

        md_parts.append("## Agenda Items")
        for item in protocol_json_data.get('agenda_items', []):
            md_parts.append(f"### {item.get('topic', 'Unnamed Agenda Item')}")
            md_parts.append(f"**Summary:** {item.get('discussion_summary', 'N/A')}")
            if item.get('decisions_made'):
                md_parts.append("**Decisions:**")
                for d in item['decisions_made']:
                    md_parts.append(f"  - {d}")
            if item.get('action_items_assigned'):
                md_parts.append("**Action Items:**")
                for ai in item['action_items_assigned']:
                    md_parts.append(f"  - {ai.get('what', 'N/A')} (Assigned: {ai.get('who', 'N/A')}, Due: {ai.get('due', 'N/A')})")
        if not protocol_json_data.get('agenda_items'): md_parts.append("- None listed")

        md_parts.append("## Overall Summary")
        md_parts.append(protocol_json_data.get('summary', 'No overall summary provided.'))

        md_parts.append("## Global Decisions")
        for d in protocol_json_data.get('decisions', []):
            md_parts.append(f"- {d.get('description', 'N/A')} (ID: {d.get('decision_id', 'N/A')})")
        if not protocol_json_data.get('decisions'): md_parts.append("- None recorded")

        md_parts.append("## Global Action Items")
        for ai in protocol_json_data.get('action_items', []):
            md_parts.append(f"- {ai.get('description', 'N/A')} (Assigned: {ai.get('assigned_to', 'N/A')}, Due: {ai.get('due_date', 'N/A')}, Status: {ai.get('status', 'N/A')}, ID: {ai.get('action_id', 'N/A')})")
        if not protocol_json_data.get('action_items'): md_parts.append("- None recorded")
        
        if protocol_json_data.get("error"): # Add error to Markdown if present
            md_parts.append("## Errors Encountered")
            md_parts.append(f"- {protocol_json_data.get('error')}")
            if protocol_json_data.get('details'):
                md_parts.append(f"  - Details: {protocol_json_data.get('details')}")

        markdown_text = "\n\n".join(md_parts)
        # --- End Markdown Generation ---

        return markdown_text, protocol_json_data

def generate_minutes(transcript_segments: List[Dict], 
                     meeting_info: Dict = None, 
                     output_dir: pathlib.Path = None, 
                     schema_json_path: str = "../schema/egl_protokoll.json") -> Tuple[pathlib.Path, pathlib.Path]:
    """
    End-to-end pipeline to generate meeting minutes.
    Now instantiates OpenAIProcessor once and passes it to map, reduce, refine functions.
    
    Args:
        transcript_segments: List of transcript segments from ASR
        meeting_info: Additional meeting metadata (e.g., date, title, participants, agenda)
        output_dir: Directory to save the generated Markdown and JSON files.
        schema_json_path: Relative path to the JSON schema for validation.
        
    Returns:
        Tuple of (path_to_markdown_file, path_to_json_file)
    """
    start_time = time.time()

    if meeting_info is None:
        meeting_info = {}
    
    # Initialize the OpenAIProcessor once for the entire pipeline run
    try:
        processor = OpenAIProcessor()
    except ValueError as e:
        print(f"Fatal Error: Could not initialize OpenAIProcessor: {e}")
        # Cannot proceed without the processor
        raise SystemExit(1) 

    # 1. Split transcript into chunks
    print("Splitting transcript into chunks...")
    text_chunks = split_transcript(transcript_segments)
    if not text_chunks:
        print("No text chunks to process. Exiting.")
        # Create empty files or handle as error
        # For now, let's allow it to proceed and generate empty/error protocol

    # 2. MAP stage: Process chunks in parallel
    print(f"Starting MAP stage for {len(text_chunks)} chunks...")
    map_stage_outputs = []
    # Using ThreadPoolExecutor to parallelize map_call
    # Pass the processor instance to each map_call
    with ThreadPoolExecutor(max_workers=min(5, os.cpu_count() or 1)) as executor:
        futures = [executor.submit(map_call, chunk, processor) for chunk in text_chunks]
        for i, future in enumerate(futures):
            try:
                map_stage_outputs.append(future.result(timeout=120)) # Increased timeout for individual map call
                print(f"  Processed chunk {i+1}/{len(text_chunks)}")
            except Exception as e:
                print(f"Error processing chunk {i+1}: {e}")
                map_stage_outputs.append({"summary": f"Error in MAP: {e}", "decisions": [], "actions": []})
    print("MAP stage completed.")

    # 3. REDUCE stage: Consolidate results
    print("Starting REDUCE stage...")
    # Pass the processor instance to reduce_results
    reduced_data = reduce_results(map_stage_outputs, processor)
    print("REDUCE stage completed.")

    # 4. REFINE stage: Generate final protocol
    print("Starting REFINE stage...")
    # Pass the processor instance to refine_to_protocol
    markdown_output, json_output = refine_to_protocol(reduced_data, meeting_info, processor, schema_path=schema_json_path)
    print("REFINE stage completed.")

    # 5. Save outputs
    if output_dir is None:
        output_dir = pathlib.Path(".") / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create a filename based on meeting title and date, or a timestamp
    base_filename = "meeting_protocol"
    if meeting_info.get('title'):
        # Sanitize title for filename
        safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in meeting_info['title'])
        safe_title = safe_title.replace(' ', '_')[:50] # Limit length
        base_filename = safe_title
    if meeting_info.get('date'):
        base_filename = f"{meeting_info['date']}_{base_filename}"
    else:
        base_filename = f"{time.strftime('%Y-%m-%d')}_{base_filename}"

    md_filename = f"{base_filename}.md"
    json_filename = f"{base_filename}.json"

    md_file_path = output_dir / md_filename
    json_file_path = output_dir / json_filename

    with open(md_file_path, 'w', encoding='utf-8') as f_md:
        f_md.write(markdown_output)
    print(f"Markdown protocol saved to: {md_file_path}")

    with open(json_file_path, 'w', encoding='utf-8') as f_json:
        json.dump(json_output, f_json, indent=4, ensure_ascii=False)
    print(f"JSON protocol saved to: {json_file_path}")

    end_time = time.time()
    print(f"Meeting minutes generation completed in {end_time - start_time:.2f} seconds.")

    return md_file_path, json_file_path
