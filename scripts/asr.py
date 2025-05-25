import replicate
import pathlib
import os

# Default Replicate model for whisper diarization
DEFAULT_MODEL = "thomasmol/whisper-diarization"
DEFAULT_VERSION = "1495a9cddc83b2203b0d8d3516e38b80fd1572ebc4bc5700ac1da56a9b3ed886"

class ReplicateASRClient:
    """Client for interacting with Replicate ASR (Automatic Speech Recognition) API."""
    def __init__(self, model_name: str = DEFAULT_MODEL, model_version: str = DEFAULT_VERSION):
        """
        Initialize the Replicate ASR client.

        Args:
            model_name: The name of the Replicate model (e.g., 'thomasmol/whisper-diarization').
            model_version: The version hash of the Replicate model.
        """
        self.model_identifier = f"{model_name}:{model_version}"

    def transcribe_audio(self, audio_path: pathlib.Path, lang: str = None, num_speakers: int = None) -> list[dict]:
        """
        Transcribe an audio file using the configured Replicate model.

        Args:
            audio_path: Path to the audio file.
            lang: Optional language code (e.g., 'de' for German, None for auto-detection).
            num_speakers: Optional number of speakers to detect. If None, auto-detects.

        Returns:
            List of segment dictionaries with speaker info and timestamps.
        
        Raises:
            RuntimeError: If transcription fails due to API errors or other issues.
        """
        try:
            with open(audio_path, "rb") as audio_file:
                prediction = replicate.run(
                    self.model_identifier,
                    input={
                        "file": audio_file,
                        "language": lang or "",  # API expects empty string for auto-detection
                        "num_speakers": num_speakers, # Pass None for auto-detection
                    },
                )
            
            if not prediction or "segments" not in prediction:
                # Handle cases where prediction is None or segments key is missing
                print(f"Warning: Replicate API returned an unexpected response: {prediction}")
                return [] # Return empty list to avoid downstream errors

            return prediction["segments"]
        except replicate.exceptions.ReplicateError as e:
            print(f"Replicate API error during transcription: {e}")
            raise RuntimeError(f"Failed to transcribe audio due to Replicate API error: {e}") from e
        except FileNotFoundError:
            print(f"Error: Audio file not found at {audio_path}")
            raise RuntimeError(f"Audio file not found: {audio_path}")
        except Exception as e:
            print(f"An unexpected error occurred during transcription: {e}")
            raise RuntimeError(f"Failed to transcribe audio due to an unexpected error: {e}") from e

# Original transcribe function, now using the client
def transcribe(audio_path: pathlib.Path, lang: str = None) -> list[dict]:
    """
    Transcribe audio file using Replicate API with speaker diarization.
    This function now utilizes the ReplicateASRClient.
    
    Args:
        audio_path: Path to the audio file
        lang: Optional language code (e.g. 'de' for German, None for auto-detection)
        
    Returns:
        List of segment dictionaries with speaker info and timestamps
    """
    # For now, we instantiate the client with default model and version.
    # This could be configured externally later (e.g., from a config file or CLI args).
    client = ReplicateASRClient()
    return client.transcribe_audio(audio_path, lang=lang)
