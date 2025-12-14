#!/usr/bin/env python3
# ABL.py – Automatic Beatmapper for Luminote 
import argparse
import csv
import numpy as np
import librosa
import os

# Note Types
TYPE_CIRCLE = 0
TYPE_SLIDER = 1

def find_audio_files(song_dir):
    """Finds master, vocals, and drums audio files."""
    files = {'master': None, 'vocals': None, 'drums': None}
    for file in os.listdir(song_dir):
        f_lower = file.lower()
        if f_lower.endswith(('.ogg', '.mp3', '.wav')):
            if 'vocal' in f_lower:
                files['vocals'] = os.path.join(song_dir, file)
            elif 'drum' in f_lower:
                files['drums'] = os.path.join(song_dir, file)
            # Find a suitable master track (not an instrumental or a stem)
            elif files.get('master') is None and all(k not in f_lower for k in ['instrumental', 'vocal', 'drum', 'bass', 'other']):
                 files['master'] = os.path.join(song_dir, file)
    
    # If no specific master found, take the first valid audio file
    if files['master'] is None:
        for file in os.listdir(song_dir):
            if file.lower().endswith(('.ogg', '.mp3', '.wav')):
                files['master'] = os.path.join(song_dir, file)
                break
                
    return files

def analyze_drums_for_circles(drum_path, sr):
    """Analyzes a drum track to find clean onsets for hit circles."""
    print("Analyzing drums for rhythm...")
    y_drums, _ = librosa.load(drum_path, sr=sr)
    onset_frames = librosa.onset.onset_detect(y=y_drums, sr=sr, backtrack=True, units='frames', wait=5, pre_avg=5, post_avg=5)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    
    # Return notes with placeholder positions. The Composer will place them intelligently.
    return [{'time': t, 'type': TYPE_CIRCLE, 'duration': 0, 'start_x': 500, 'end_x': 500} for t in onset_times]

def analyze_vocals_for_sliders(vocal_path, sr):
    """Analyzes a vocal track to find sustained notes and pitch contours for follow-path sliders."""
    print("Analyzing vocals for melody and flow...")
    y_vocals, _ = librosa.load(vocal_path, sr=sr)
    # Detect onsets of vocal phrases
    onsets = librosa.onset.onset_detect(y=y_vocals, sr=sr, backtrack=True, units='time', wait=0.15, pre_avg=0.15, post_avg=0.15)
    
    sliders = []
    i = 0
    while i < len(onsets):
        start_time = onsets[i]
        
        # Determine the end time of the vocal phrase
        end_time = start_time + 1.0  # Default max duration
        if i + 1 < len(onsets):
            # End just before the next phrase starts, or cap at 2 seconds
            end_time = min(onsets[i+1] - 0.05, start_time + 2.0)
        
        duration = end_time - start_time
        
        if duration > 0.25:  # Only map vocal phrases longer than 250ms
            # Get pitch at the start of the phrase
            start_sample = int(start_time * sr)
            start_window = y_vocals[start_sample : start_sample + int(0.1 * sr)]
            f0_start, voiced_start, _ = librosa.pyin(start_window, fmin=75, fmax=1200, sr=sr)
            start_pitch = np.median(f0_start[voiced_start]) if np.any(voiced_start) else 0
            
            # Get pitch at the end of the phrase
            end_sample = int(end_time * sr)
            end_window = y_vocals[end_sample - int(0.1 * sr) : end_sample]
            f0_end, voiced_end, _ = librosa.pyin(end_window, fmin=75, fmax=1200, sr=sr)
            end_pitch = np.median(f0_end[voiced_end]) if np.any(voiced_end) else 0
            
            # If we found a valid pitch at both start and end, create a slider
            if start_pitch > 0 and end_pitch > 0:
                # Map MIDI pitch (C2-C6) to X coordinates (100-900)
                start_x = int(np.clip((librosa.hz_to_midi(start_pitch) - 40) / 48, 0, 1) * 800 + 100)
                end_x = int(np.clip((librosa.hz_to_midi(end_pitch) - 40) / 48, 0, 1) * 800 + 100)
                
                sliders.append({'time': start_time, 'type': TYPE_SLIDER, 'duration': int(duration * 1000), 'start_x': start_x, 'end_x': end_x})
        i += 1
    return sliders

def generate_beatmap(song_dir, difficulty='normal'):
    audio_files = find_audio_files(song_dir)
    sr = 44100  # Use a consistent sample rate for all analysis
    
    all_notes = []
    
    # --- PATH 1: uses separated stems ---
    if audio_files['vocals'] and audio_files['drums']:
        print("Vocal and Drum stems found! Using Holy Grail mapping mode.")
        drum_circles = analyze_drums_for_circles(audio_files['drums'], sr)
        vocal_sliders = analyze_vocals_for_sliders(audio_files['vocals'], sr)
        all_notes = drum_circles + vocal_sliders
        
    # --- PATH 2: uses master track ---
    else:
        print("Stems not found. Falling back to HPSS analysis on master track.")
        if not audio_files['master']:
            print(f"Error: No master audio file found in '{song_dir}'"); return
        y, _ = librosa.load(audio_files['master'], sr=sr)
        y_harm, y_perc = librosa.effects.hpss(y)
        
        # Generate simple circles from percussive track (similar to Tier 1)
        onsets = librosa.onset.onset_detect(y=y_perc, sr=sr, units='time')
        # Use simple pitch detection on harmonic track for positioning
        for t in onsets:
            start_sample = int(t * sr)
            f0, voiced, _ = librosa.pyin(y_harm[start_sample : start_sample + int(0.1*sr)], fmin=75, fmax=1200, sr=sr)
            pitch = np.median(f0[voiced]) if np.any(voiced) else 0
            x_pos = 500
            if pitch > 0:
                x_pos = int(np.clip((librosa.hz_to_midi(pitch) - 40) / 48, 0, 1) * 800 + 100)
            all_notes.append({'time': t, 'type': TYPE_CIRCLE, 'duration': 0, 'start_x': x_pos, 'end_x': x_pos})

    # --- The Composer: Merge, de-conflict, and add flow to the notes ---
    print("Composing final beatmap from analyzed notes...")
    if not all_notes:
        print("No notes were generated. Aborting."); return

    all_notes.sort(key=lambda n: n['time'])
    
    final_map_notes = []
    last_event_end_time = -1.0
    # Minimum gap between interactive elements, varies by difficulty
    min_gap_timings = {'easy': 0.200, 'normal': 0.150, 'hard': 0.100}
    min_gap = min_gap_timings.get(difficulty, 0.150)

    last_x_pos = 500

    for note in all_notes:
        # Check if the note starts too soon after the last one ends
        if note['time'] > last_event_end_time + min_gap:
            
            # Apply flow logic: place circles relative to the end of the last object
            if note['type'] == TYPE_CIRCLE:
                note['start_x'] = last_x_pos
                note['end_x'] = note['start_x']

            final_map_notes.append(note)
            
            # Update the end time of the last event
            last_event_end_time = note['time']
            if note['type'] == TYPE_SLIDER:
                last_event_end_time += note['duration'] / 1000.0
            
            # Update the last known X position for flow
            last_x_pos = note['end_x']

    # Convert to final CSV format
    final_csv_data = []
    for note in final_map_notes:
        final_csv_data.append((
            int(note['time'] * 1000),
            note['start_x'],
            note['type'],
            note['duration'],
            note['end_x']
        ))
        
    # --- Output CSV to song directory ---
    output_filename = f"song_{difficulty}.csv"
    output_path = os.path.join(song_dir, output_filename)
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(final_csv_data)
    
    print(f"\nSuccess! Generated {len(final_csv_data)} notes.")
    print(f"Beatmap saved to: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="ABL Tier 3: The Holy Grail Beatmapper")
    parser.add_argument('song_directory', help="Path to the song's directory (may contain vocal/drum stems)")
    parser.add_argument('-d', '--difficulty', choices=['easy', 'normal', 'hard'], default='normal', help="Set the difficulty, which affects note density")
    args = parser.parse_args()
    
    generate_beatmap(args.song_directory, args.difficulty)
