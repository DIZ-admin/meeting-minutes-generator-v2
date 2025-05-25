#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import sys
from datetime import datetime
from typing import Dict, Optional

from .asr import transcribe
from .map_reduce_refine import generate_minutes
from .telegram_notify import send_files

def extract_meeting_info(filename: str) -> Dict:
    """
    Extract meeting information from the filename or provide defaults
    
    Args:
        filename: Name of the audio file
        
    Returns:
        Dictionary with meeting metadata
    """
    # Default meeting info
    meeting_info = {
        "title": "Protokoll eGL",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "location": "Online Meeting",
        "chair": "",
        "author": "AI Assistant",
        "participants": [],
        "absent": []
    }
    
    # Try to extract date from filename if it matches pattern like "meeting_2025-06-01"
    # or "eGL_2025-06-01" format
    import re
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if date_match:
        meeting_info["date"] = date_match.group(1)
    
    return meeting_info

def process_audio(audio_path: pathlib.Path, output_dir: Optional[pathlib.Path] = None,
                 lang: Optional[str] = None) -> None:
    """
    Process an audio file to generate meeting minutes
    
    Args:
        audio_path: Path to the audio file
        output_dir: Directory to save the output files (default: ./output/[filename])
        lang: Optional language code (e.g. 'de' for German)
    """
    try:
        # Validate that audio file exists
        if not audio_path.exists():
            print(f"Error: Audio file not found: {audio_path}")
            sys.exit(1)
        
        # Create output directory
        if output_dir is None:
            output_dir = pathlib.Path("/data/out") / audio_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Processing: {audio_path}")
        print(f"Output directory: {output_dir}")
        
        # Step 1: Transcribe audio with speaker diarization
        print("Starting audio transcription...")
        # Get language from env var if not provided
        if not lang:
            lang = os.getenv("TRANSCRIPTION_LANG", "de")  # Default to German
        transcript_segments = transcribe(audio_path, lang)
        print(f"Transcription complete: {len(transcript_segments)} segments")
        
        # Save raw transcript for debugging
        transcript_path = output_dir / "transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_segments, f, ensure_ascii=False, indent=2)
        
        # Step 2: Extract meeting info from filename
        meeting_info = extract_meeting_info(audio_path.stem)
        
        # Step 3: Generate meeting minutes
        print("Generating meeting minutes...")
        markdown, json_data = generate_minutes(transcript_segments, meeting_info)
        
        # Step 4: Save output files
        md_file = output_dir / "minutes.md"
        json_file = output_dir / "minutes.json"
        
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"Minutes generated successfully: {md_file}")
        
        # Step 5: Send to Telegram
        send_files(md_file, json_file)
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        sys.exit(1)

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Generate meeting minutes from audio recordings")
    parser.add_argument("audio", help="Path to audio file (wav/m4a/mp3)")
    parser.add_argument("--lang", help="Language code (e.g. 'de' for German, default from env var or 'de')")
    parser.add_argument("--output", help="Output directory (default: ./output/[filename])")
    
    args = parser.parse_args()
    
    # Convert paths
    audio_path = pathlib.Path(args.audio)
    output_dir = pathlib.Path(args.output) if args.output else None
    
    # Process the audio file
    process_audio(audio_path, output_dir, args.lang)

if __name__ == "__main__":
    main()
