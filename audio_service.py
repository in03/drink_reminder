import os
import glob
import random
import asyncio
import subprocess
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class AudioFile:
    """Represents an audio file with metadata"""
    path: str
    category: str  # 'drink_reminder' or 'praise'
    severity_level: int  # 1-5 based on filename
    variant: Optional[int] = None  # variant number if present


class AudioService:
    """Service for playing audio cues based on severity levels and improvement factors"""
    
    def __init__(self, audio_directory: str = "data/audio"):
        self.audio_directory = audio_directory
        self.audio_files: Dict[str, Dict[int, List[AudioFile]]] = {
            'drink_reminder': {},
            'praise': {}
        }
        self._scan_audio_files()
    
    def _scan_audio_files(self):
        """Scan audio directory for available files and organize by category/severity"""
        if not os.path.exists(self.audio_directory):
            print(f"Warning: Audio directory '{self.audio_directory}' not found")
            return
        
        # Find all mp3 files matching our patterns
        patterns = [
            f"{self.audio_directory}/drink_reminder_s*.mp3",
            f"{self.audio_directory}/praise_s*.mp3"
        ]
        
        for pattern in patterns:
            for file_path in glob.glob(pattern):
                audio_file = self._parse_audio_filename(file_path)
                if audio_file:
                    category = audio_file.category
                    severity = audio_file.severity_level
                    
                    if severity not in self.audio_files[category]:
                        self.audio_files[category][severity] = []
                    
                    self.audio_files[category][severity].append(audio_file)
        
        # Log discovered files
        self._log_available_files()
    
    def _parse_audio_filename(self, file_path: str) -> Optional[AudioFile]:
        """Parse audio filename to extract metadata"""
        filename = os.path.basename(file_path)
        
        # Remove extension
        name_without_ext = os.path.splitext(filename)[0]
        
        # Parse drink_reminder_s{n}[_v{n}] or praise_s{n}[_v{n}]
        if name_without_ext.startswith('drink_reminder_s'):
            category = 'drink_reminder'
            rest = name_without_ext[len('drink_reminder_s'):]
        elif name_without_ext.startswith('praise_s'):
            category = 'praise'
            rest = name_without_ext[len('praise_s'):]
        else:
            return None
        
        # Extract severity level and optional variant
        parts = rest.split('_v')
        try:
            severity_level = int(parts[0])
            variant = int(parts[1]) if len(parts) > 1 else None
            
            return AudioFile(
                path=file_path,
                category=category,
                severity_level=severity_level,
                variant=variant
            )
        except ValueError:
            print(f"Warning: Could not parse audio file '{filename}'")
            return None
    
    def _log_available_files(self):
        """Log discovered audio files for debugging"""
        total_files = sum(
            len(files) for category_files in self.audio_files.values() 
            for files in category_files.values()
        )
        
        if total_files == 0:
            print("No audio files found")
            return
        
        print(f"🔊 Audio Service: Found {total_files} audio files")
        for category, severity_dict in self.audio_files.items():
            if severity_dict:
                severity_levels = sorted(severity_dict.keys())
                variants_info = []
                for level in severity_levels:
                    file_count = len(severity_dict[level])
                    variants_info.append(f"s{level}({file_count})")
                
                print(f"  - {category}: {', '.join(variants_info)}")
    
    def _map_severity_to_audio_level(self, severity_value: float, category: str) -> Optional[int]:
        """Map severity/improvement factor to available audio severity levels"""
        available_levels = sorted(self.audio_files[category].keys()) if self.audio_files[category] else []
        
        if not available_levels:
            return None
        
        min_level = min(available_levels)
        max_level = max(available_levels)
        
        if category == 'drink_reminder':
            # Map severity 1-30 to available audio levels
            # Clamp input to reasonable range
            clamped_severity = max(1, min(30, severity_value))
            
            # Scale to 0-1 range
            normalized = (clamped_severity - 1) / 29  # 1-30 becomes 0-1
            
            # Map to available audio levels
            audio_level = min_level + normalized * (max_level - min_level)
            return max(min_level, min(max_level, round(audio_level)))
        
        elif category == 'praise':
            # Map improvement factor 0.0-6.0 to available audio levels  
            # Higher improvement factor = higher praise level
            clamped_factor = max(0.0, min(6.0, severity_value))
            
            # Scale to 0-1 range
            normalized = clamped_factor / 6.0
            
            # Map to available audio levels
            audio_level = min_level + normalized * (max_level - min_level)
            return max(min_level, min(max_level, round(audio_level)))
        
        return None
    
    def _select_audio_file(self, category: str, severity_value: float) -> Optional[AudioFile]:
        """Select appropriate audio file based on category and severity/improvement factor"""
        audio_level = self._map_severity_to_audio_level(severity_value, category)
        
        if audio_level is None or audio_level not in self.audio_files[category]:
            return None
        
        # Get all files for this level (includes variants)
        available_files = self.audio_files[category][audio_level]
        
        # Randomly select one for variety
        return random.choice(available_files)
    
    async def play_drink_reminder_audio(self, severity_level: int) -> bool:
        """Play audio for drink reminder based on severity level (1-30)"""
        return await self._play_audio('drink_reminder', severity_level)
    
    async def play_praise_audio(self, improvement_factor: float) -> bool:
        """Play audio for praise based on hydration improvement factor (0.0-6.0)"""
        return await self._play_audio('praise', improvement_factor)
    
    async def _play_audio(self, category: str, severity_value: float) -> bool:
        """Internal method to play audio file"""
        try:
            audio_file = self._select_audio_file(category, severity_value)
            
            if not audio_file:
                print(f"No audio file available for {category} with severity {severity_value}")
                return False
            
            # Play audio file asynchronously (non-blocking)
            # Using afplay on macOS for simple playback
            process = await asyncio.create_subprocess_exec(
                'afplay', audio_file.path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Don't wait for completion - let it play in background
            variant_info = f"_v{audio_file.variant}" if audio_file.variant else ""
            print(f"🔊 Playing {category}_s{audio_file.severity_level}{variant_info}.mp3 (severity: {severity_value})")
            
            return True
            
        except Exception as e:
            print(f"Error playing audio: {e}")
            return False
    
    def get_audio_stats(self) -> Dict:
        """Get statistics about available audio files"""
        stats = {}
        
        for category, severity_dict in self.audio_files.items():
            if severity_dict:
                levels = sorted(severity_dict.keys())
                total_files = sum(len(files) for files in severity_dict.values())
                max_variants = max(len(files) for files in severity_dict.values()) if severity_dict else 0
                
                stats[category] = {
                    'levels': levels,
                    'total_files': total_files,
                    'max_variants': max_variants,
                    'level_range': f"s{min(levels)}-s{max(levels)}" if levels else "none"
                }
            else:
                stats[category] = {
                    'levels': [],
                    'total_files': 0,
                    'max_variants': 0,
                    'level_range': "none"
                }
        
        return stats


# Global audio service instance
audio_service = AudioService() 