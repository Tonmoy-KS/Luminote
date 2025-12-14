#!/usr/bin/env python3
# Luminote.py
import pygame
import csv
import os
import time
import json
import random
import math
from collections import deque
from pydub import AudioSegment
import configparser

# --- Constants ---
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
PLAYFIELD_X = 192
PLAYFIELD_WIDTH = 640
TARGET_Y = 650
BASE_NOTE_SPEED_PPS = 900

# Game States
STATE_MENU = 0
STATE_PLAYING = 1
STATE_RESULTS = 2
STATE_SONG_SELECT = 3

# Note Types
TYPE_CIRCLE = 0
TYPE_SLIDER = 1

# --- SkinManager ---
class SkinManager:
    """Handles loading and managing all visual and audio assets from skin folders."""
    def __init__(self, base_path="Skins"):
        self.base_path = base_path
        self.default_skin_path = os.path.join(base_path, "Default")
        self.assets = {}
        self.config = configparser.ConfigParser()
        self.load_skin("Default")

    def load_skin(self, skin_name):
        print(f"Loading skin: {skin_name}...")
        self.assets = {}
        self.config = configparser.ConfigParser()
        skin_path = os.path.join(self.base_path, skin_name)
        
        # Load config, with fallback to Default config first
        self.config.read(os.path.join(self.default_skin_path, 'skin.ini'))
        if os.path.exists(os.path.join(skin_path, 'skin.ini')):
            self.config.read(os.path.join(skin_path, 'skin.ini'))

        # List of assets to load. The game's code will refer to these keys.
        asset_files = ['note.png', 'cursor.png', 'hitsound.wav']
        for asset in asset_files:
            path = os.path.join(skin_path, asset)
            if not os.path.exists(path):
                path = os.path.join(self.default_skin_path, asset) # Fallback to Default
            
            try:
                if asset.endswith('.png'):
                    self.assets[asset] = pygame.image.load(path).convert_alpha()
                elif asset.endswith('.wav'):
                    self.assets[asset] = pygame.mixer.Sound(path)
            except Exception as e:
                print(f"Warning: Could not load asset '{asset}': {e}")
    
    def get_color(self, section, key):
        try:
            color_str = self.config.get(section, key)
            return tuple(map(int, color_str.split(',')))
        except:
            return (255, 0, 255) # Bright pink fallback for missing colors
    
    def get_font(self, section, size_key):
        try:
            # Fonts are always loaded from the Default skin folder to ensure they exist
            font_name = self.config.get('Fonts', 'FontName')
            font_size = self.config.getint(section, size_key)
            font_path = os.path.join(self.default_skin_path, font_name)
            return pygame.font.Font(font_path, font_size)
        except Exception as e:
            # print(f"Font error: {e}")
            return pygame.font.Font(None, 36) # Pygame default fallback

# --- Classes ---
class Note:
    """Represents a single game object, either a circle or a follow-path slider."""
    def __init__(self, ts, start_x, n_type, n_dur, end_x, skin, note_speed):
        self.arrival_time_ms = ts
        self.start_x = start_x
        self.note_type = n_type
        self.duration_ms = n_dur
        self.end_x = end_x
        self.skin = skin
        self.note_speed = note_speed
        
        self.y_pos = 0.0
        self.alive = True
        self.is_held = False
        self.follow_circle_pos = (self.start_x, TARGET_Y)
        
        # Scale note texture from skin
        note_size = int(self.skin.config.get('General', 'NoteSize', fallback=80))
        self.note_texture = pygame.transform.scale(self.skin.assets['note.png'], (note_size, note_size))
        self.note_radius = note_size / 2

    def update(self, dt, current_game_time_ms):
        self.y_pos += self.note_speed * dt
        if self.y_pos > SCREEN_HEIGHT + self.note_radius * 2:
            self.alive = False

        if self.note_type == TYPE_SLIDER and self.is_held:
            # Update follow circle position based on time
            time_into_slider = current_game_time_ms - self.arrival_time_ms
            progress = max(0, min(1, time_into_slider / self.duration_ms))
            
            current_x = self.start_x + (self.end_x - self.start_x) * progress
            self.follow_circle_pos = (current_x, TARGET_Y)

    def draw(self, screen):
        # Draw slider body for follow-path sliders
        if self.note_type == TYPE_SLIDER:
            start_pos = (self.start_x, self.y_pos)
            end_pos_y = self.y_pos + self.note_speed * (self.duration_ms / 1000.0)
            end_pos = (self.end_x, end_pos_y)
            
            body_color = self.skin.get_color('Colors', 'SliderBody')
            border_color = self.skin.get_color('Colors', 'SliderBorder')
            
            pygame.draw.line(screen, body_color, start_pos, end_pos, int(self.note_radius * 2))
            pygame.draw.line(screen, border_color, start_pos, end_pos, int(self.note_radius * 2) + 4)
            
            # Draw follow circle if being held
            if self.is_held:
                follow_radius = int(self.skin.config.get('General', 'FollowCircleSize', fallback=60))
                pygame.draw.circle(screen, border_color, self.follow_circle_pos, follow_radius, 4)

        # Draw note head
        head_pos = (self.start_x, self.y_pos)
        screen.blit(self.note_texture, (head_pos[0] - self.note_radius, head_pos[1] - self.note_radius))

class Particle:
    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color
        self.vx, self.vy = random.uniform(-200, 200), random.uniform(-200, 0)
        self.life, self.max_life, self.size = 1.0, 0.6, random.uniform(3, 8)
    def update(self, dt):
        self.x += self.vx * dt; self.y += self.vy * dt
        self.vy += 400 * dt; self.life -= dt / self.max_life; self.size *= 0.98
    def draw(self, screen):
        if self.life > 0:
            alpha = int(255 * self.life); surf = pygame.Surface((self.size*2, self.size*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color[:3], alpha), (self.size, self.size), self.size)
            screen.blit(surf, (self.x - self.size, self.y - self.size))

class FeedbackText:
    def __init__(self, text, color, x, y, font):
        self.text, self.color, self.x, self.y, self.font = text, color, x, y, font
        self.timer, self.vel_y, self.scale = 0.8, -150, 1.0
    def update(self, dt):
        self.y += self.vel_y * dt; self.timer -= dt
        self.scale += 1.5 * dt; self.vel_y *= 0.95
    def draw(self, screen):
        if self.timer > 0:
            try:
                # Recreate font object with scaled size
                scaled_font = pygame.font.Font(self.font.name, int(self.font.get_height() * self.scale))
                surf = scaled_font.render(self.text, True, self.color)
                surf.set_alpha(int(255 * (self.timer / 0.8)))
                screen.blit(surf, (self.x - surf.get_width() // 2, self.y - surf.get_height() // 2))
            except: pass # Failsafe if font disappears

# --- Utility Functions ---
def load_beatmap(filename):
    beatmap = []
    try:
        with open(filename, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 5 and row[0].strip():
                    beatmap.append(tuple(map(int, row))) # ts, start_x, type, duration, end_x
        return sorted(beatmap)
    except Exception as e:
        print(f"Error loading beatmap {filename}: {e}."); return []

def calculate_grade_and_accuracy(stats):
    hit_counts = stats['hit_counts']
    total_objects = sum(hit_counts.values())
    if total_objects == 0: return 0.0, "N/A", ""
    achieved = (hit_counts['300'] * 300 + hit_counts['100'] * 100 + hit_counts['50'] * 50)
    max_possible = total_objects * 300
    accuracy = (achieved / max_possible) * 100
    if math.isclose(accuracy, 100.0): return 100.0, "E", "Ethereal"
    if accuracy >= 97: return accuracy, "SSS", "Sublime"
    elif accuracy >= 95: return accuracy, "SS+", "Beyond Superb"
    elif accuracy >= 94: return accuracy, "SS", "Serious"
    elif accuracy >= 91: return accuracy, "S+", "Staggering"
    elif accuracy >= 90: return accuracy, "S", "Superb"
    elif accuracy >= 88: return accuracy, "A+", "Astounding"
    elif accuracy >= 85: return accuracy, "A", "Awesome"
    elif accuracy >= 80: return accuracy, "A-", "Amazing"
    elif accuracy >= 75: return accuracy, "B+", "Best"
    elif accuracy >= 60: return accuracy, "B", "Benevolent"
    elif accuracy >= 55: return accuracy, "C", "Cool"
    elif accuracy >= 40: return accuracy, "D+", "Above Decent"
    elif accuracy >= 30: return accuracy, "D", "Decent"
    elif accuracy >= 20: return accuracy, "D-", "Under Decent"
    else: return accuracy, "F", "Failure"

def scan_song_library(songs_dir="Songs"):
    library = []
    for song_folder in os.listdir(songs_dir):
        song_path = os.path.join(songs_dir, song_folder)
        if os.path.isdir(song_path):
            song_data = {'name': song_folder, 'path': song_path, 'audio': None, 'difficulties': {}}
            for file in os.listdir(song_path):
                if file.lower().endswith(('.ogg', '.mp3', '.wav')) and 'instrumental' not in file.lower() and 'vocals' not in file.lower() and 'drums' not in file.lower():
                    song_data['audio'] = file
                elif file.lower().startswith('song_') and file.lower().endswith('.csv'):
                    diff_name = file.lower().replace('song_', '').replace('.csv', '')
                    song_data['difficulties'][diff_name] = file
            if song_data['audio'] and song_data['difficulties']: library.append(song_data)
    return library

# --- Screen Functions ---
def menu_screen(screen, skin):
    font_title = skin.get_font('Menu', 'TitleSize')
    font_prompt = skin.get_font('Menu', 'PromptSize')
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type in [pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN]: return True
        screen.fill(skin.get_color('Colors', 'Background'))
        title = font_title.render("Luminote", True, skin.get_color('Colors', 'Font'))
        prompt = font_prompt.render("Click or Enter to Play", True, skin.get_color('Colors', 'Font'))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 250))
        screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, 450))
        pygame.display.flip()

def song_select_screen(screen, library, skin):
    font_title = skin.get_font('Select', 'TitleSize')
    font_song = skin.get_font('Select', 'SongSize')
    font_diff = skin.get_font('Select', 'DiffSize')
    font_mod = skin.get_font('Select', 'ModSize')
    selected_song_idx, active_mods = 0, set()
    mods = {'HR': 'Hard Rock', 'DT': 'Double Time'}
    mod_rects = {mod_key: pygame.Rect(50 + i * 180, SCREEN_HEIGHT - 60, 150, 40) for i, mod_key in enumerate(mods.keys())}
    while True:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return None, None, None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_DOWN: selected_song_idx = (selected_song_idx + 1) % len(library)
                if event.key == pygame.K_UP: selected_song_idx = (selected_song_idx - 1 + len(library)) % len(library)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for mod_key, rect in mod_rects.items():
                    if rect.collidepoint(mouse_pos):
                        if mod_key in active_mods: active_mods.remove(mod_key)
                        else: active_mods.add(mod_key)
                if library:
                    selected_song = library[selected_song_idx]
                    for i, diff_name in enumerate(sorted(selected_song['difficulties'].keys())):
                        diff_rect = pygame.Rect(700, 180 + i * 50 - 5, 250, 40)
                        if diff_rect.collidepoint(mouse_pos):
                            beatmap_file = os.path.join(selected_song['path'], selected_song['difficulties'][diff_name])
                            audio_file = os.path.join(selected_song['path'], selected_song['audio'])
                            return audio_file, beatmap_file, list(active_mods)
        screen.fill(skin.get_color('Colors', 'Background'))
        title_surf = font_title.render("Select a Song", True, skin.get_color('Colors', 'Font'))
        screen.blit(title_surf, (SCREEN_WIDTH//2 - title_surf.get_width()//2, 30))
        for i, song in enumerate(library):
            y_pos = 120 + i * 60
            color = skin.get_color('Colors', 'Selected') if i == selected_song_idx else skin.get_color('Colors', 'Font')
            if i == selected_song_idx: pygame.draw.rect(screen, skin.get_color('Colors', 'Panel'), (50, y_pos - 5, 600, 50))
            song_surf = font_song.render(song['name'], True, color)
            screen.blit(song_surf, (60, y_pos))
        if library:
            selected_song = library[selected_song_idx]
            diff_title_surf = font_song.render("Difficulties", True, skin.get_color('Colors', 'Font'))
            screen.blit(diff_title_surf, (700, 120))
            for i, diff_name in enumerate(sorted(selected_song['difficulties'].keys())):
                y_pos, color = 180 + i * 50, skin.get_color('Colors', 'Font')
                if pygame.Rect(700, y_pos - 5, 250, 40).collidepoint(mouse_pos): color = skin.get_color('Colors', 'Selected')
                diff_surf = font_diff.render(diff_name.capitalize(), True, color)
                screen.blit(diff_surf, (710, y_pos))
        for mod_key, rect in mod_rects.items():
            color = skin.get_color('Colors', 'Panel') if mod_key in active_mods else (30,30,30)
            pygame.draw.rect(screen, color, rect, border_radius=5)
            mod_surf = font_mod.render(mods[mod_key], True, skin.get_color('Colors', 'Font'))
            screen.blit(mod_surf, (rect.x + (rect.w-mod_surf.get_width())//2, rect.y + (rect.h-mod_surf.get_height())//2))
        pygame.display.flip()

def results_screen(screen, stats, skin):
    font_grade = skin.get_font('Results', 'GradeSize'); font_name = skin.get_font('Results', 'NameSize'); font_stat = skin.get_font('Results', 'StatSize')
    font_color = skin.get_color('Colors', 'Font')
    accent_color = skin.get_color('Colors', 'Accent')
    hit_colors = { '300': (0, 255, 100), '100': (255, 255, 0), '50': (255, 165, 0), 'miss': (255, 50, 50) }
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type in [pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN]: return True
        screen.fill(skin.get_color('Colors', 'Background'))
        acc, grade, name = calculate_grade_and_accuracy(stats)
        grade_surf = font_grade.render(grade, True, font_color); screen.blit(grade_surf, (SCREEN_WIDTH//2-grade_surf.get_width()//2, 100))
        name_surf = font_name.render(name, True, accent_color); screen.blit(name_surf, (SCREEN_WIDTH//2-name_surf.get_width()//2, 320))
        y_pos = 420
        acc_surf = font_stat.render(f"Accuracy: {acc:.2f}%", True, font_color); screen.blit(acc_surf, (PLAYFIELD_X, y_pos)); y_pos += 55
        score_surf = font_stat.render(f"Score: {stats['score']:010d}", True, font_color); screen.blit(score_surf, (PLAYFIELD_X, y_pos)); y_pos += 55
        combo_surf = font_stat.render(f"Max Combo: {stats['max_combo']}", True, font_color); screen.blit(combo_surf, (PLAYFIELD_X, y_pos)); y_pos += 55
        hit_y = 420
        for ht in ['300', '100', '50', 'miss']:
            txt = font_stat.render(f"{ht}: {stats['hit_counts'][ht]}", True, hit_colors[ht]); screen.blit(txt, (PLAYFIELD_X + 350, hit_y)); hit_y += 45
        prompt = font_stat.render("Click or Enter to Continue", True, skin.get_color('Colors', 'Panel')); screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, SCREEN_HEIGHT - 60))
        pygame.display.flip()

# --- MODIFIED: Game Loop ---
def game_loop(screen, audio_file, beatmap_file, active_mods, skin):
    # Apply Modifiers
    note_speed, dt_rate = BASE_NOTE_SPEED_PPS, 1.0
    hit_windows = {'300': 25, '100': 55, '50': 85}
    if 'HR' in active_mods: hit_windows = {k: v*0.8 for k, v in hit_windows.items()}
    if 'DT' in active_mods: dt_rate = 1.5; note_speed *= dt_rate
    scroll_time_ms = int((TARGET_Y / note_speed) * 1000)

    # Load Beatmap & Audio
    beatmap = load_beatmap(beatmap_file)
    if not beatmap: return {}, True
    if 'DT' in active_mods:
        sound = AudioSegment.from_file(audio_file).speedup(playback_speed=dt_rate)
        audio_file = os.path.join(os.path.dirname(audio_file), "temp_dt_audio.ogg")
        sound.export(audio_file, format="ogg")
        beatmap = [(int(ts/dt_rate), sx, nt, int(dr/dt_rate), ex) for ts,sx,nt,dr,ex in beatmap]
    
    pygame.mixer.music.load(audio_file)
    pygame.mixer.music.play()
    
    # Game State Init
    clock = pygame.time.Clock(); notes, particles, feedbacks = [], [], []
    held_slider = None
    hit_sound = skin.assets.get('hitsound.wav')
    if hit_sound: hit_sound.set_volume(0.5)
    cursor_img = skin.assets.get('cursor.png')

    pygame.mouse.set_visible(False)
    stats = {'score': 0, 'combo': 0, 'max_combo': 0, 'hit_counts': {'300': 0, '100': 0, '50': 0, 'miss': 0}}
    next_note_idx, start_time_ms, last_time = 0, pygame.time.get_ticks(), time.time()
    paused, fadeout_start = False, None
    
    while True: # Main loop
        mouse_pos = pygame.mouse.get_pos(); mouse_x, mouse_y = mouse_pos
        dt = time.time() - last_time; last_time = time.time()
        current_game_time = pygame.time.get_ticks() - start_time_ms

        if next_note_idx >= len(beatmap) and not notes and not held_slider:
            if not fadeout_start: pygame.mixer.music.fadeout(2000); fadeout_start = current_game_time
            elif current_game_time - fadeout_start > 2000: pygame.mouse.set_visible(True); return stats, True

        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.mouse.set_visible(True); return None, False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                paused = not paused
                if paused: pygame.mixer.music.pause()
                else: pygame.mixer.music.unpause()
            
            if not paused and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit_note = None; min_y_dist = float('inf')
                for note in notes:
                    if abs(note.y_pos - TARGETY) > hit_windows['50']: continue
                    if abs(note.start_x - mouse_x) > note.note_radius * 2: continue
                    y_dist = abs(note.y_pos - TARGET_Y)
                    if y_dist < min_y_dist: min_y_dist, hit_note = y_dist, note
                
                if hit_note:
                    if hit_sound: hit_sound.play()
                    if hit_note.note_type == TYPE_CIRCLE:
                        if min_y_dist <= hit_windows['300']: hit_type = '300'
                        elif min_y_dist <= hit_windows['100']: hit_type = '100'
                        else: hit_type = '50'
                        stats['score'] += HIT_VALUES[hit_type]*(stats['combo']+1); stats['combo']+=1
                        stats['hit_counts'][hit_type] += 1
                        feedbacks.append(FeedbackText(hit_type, (0,255,0), hit_note.start_x, TARGET_Y, skin.get_font('UI','ScoreSize')))
                        notes.remove(hit_note)
                    elif hit_note.note_type == TYPE_SLIDER:
                        held_slider = hit_note; held_slider.is_held = True

        if paused: continue

        # --- Game Logic ---
        stats['max_combo'] = max(stats['max_combo'], stats['combo'])
        if held_slider:
            dist = math.hypot(mouse_x - held_slider.follow_circle_pos[0], mouse_y - held_slider.follow_circle_pos[1])
            slider_break = not pygame.mouse.get_pressed()[0] or dist > int(skin.config.get('General', 'FollowCircleSize', fallback=60))
            if slider_break:
                stats['combo'] = 0; stats['hit_counts']['miss'] += 1; notes.remove(held_slider); held_slider = None
            elif current_game_time >= held_slider.arrival_time_ms + held_slider.duration_ms:
                stats['score'] += 300*(stats['combo']+1); stats['combo']+=1; stats['hit_counts']['300'] += 1
                notes.remove(held_slider); held_slider = None

        for note in notes[:]:
            if note == held_slider: continue
            if note.y_pos > TARGET_Y + hit_windows['50']:
                notes.remove(note); stats['combo'] = 0; stats['hit_counts']['miss'] += 1

        while next_note_idx < len(beatmap) and current_game_time >= beatmap[next_note_idx][0] - scroll_time_ms:
            ts, sx, nt, dr, ex = beatmap[next_note_idx]
            notes.append(Note(ts, sx, nt, dr, ex, skin, note_speed))
            next_note_idx += 1
        
        for elem in notes + particles + feedbacks: elem.update(dt, current_game_time)
        particles = [p for p in particles if p.life > 0]; feedbacks = [fb for fb in feedbacks if fb.timer > 0]

        # --- Drawing ---
        screen.fill(skin.get_color('Colors', 'Background'))
        pygame.draw.rect(screen, skin.get_color('Colors', 'Playfield'), (PLAYFIELD_X, 0, PLAYFIELD_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(screen, skin.get_color('Colors', 'JudgementLine'), (PLAYFIELD_X, TARGET_Y), (PLAYFIELD_X + PLAYFIELD_WIDTH, TARGET_Y), 4)
        for note in notes: note.draw(screen)
        for p in particles: p.draw(screen)
        for fb in feedbacks: fb.draw(screen)
        if cursor_img: screen.blit(cursor_img, (mouse_pos[0] - cursor_img.get_width()//2, mouse_pos[1] - cursor_img.get_height()//2))
        
        font_score = skin.get_font('UI', 'ScoreSize')
        score_surf = font_score.render(f"{stats['score']:010d}", True, skin.get_color('Colors', 'Font'))
        screen.blit(score_surf, (20, 20))
        
        pygame.display.flip()
        clock.tick(240)
    
    # This return is for when the loop is broken by QUIT
    pygame.mouse.set_visible(True)
    return None, False


def main():
    pygame.init(); pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Luminote")
    
    # Create default skin structure if it doesn't exist
    os.makedirs("Skins/Default", exist_ok=True)
    os.makedirs("Songs", exist_ok=True)
    if not os.path.exists("Skins/Default/skin.ini"):
        with open("Skins/Default/skin.ini", "w") as f:
            f.write("[General]\nNoteSize=80\nFollowCircleSize=60\n\n[Colors]\nBackground=10,10,15\nFont=255,255,255\nAccent=135,206,235\nSelected=255,255,0\nPanel=50,50,50\nPlayfield=20,20,25\nJudgementLine=255,255,255\nSliderBody=100,100,100\nSliderBorder=255,255,255\n\n[Fonts]\nFontName=font.ttf\n\n[UI]\nScoreSize=36\n\n[Menu]\nTitleSize=140\nPromptSize=60\n\n[Select]\nTitleSize=80\nSongSize=50\nDiffSize=40\nModSize=35\n\n[Results]\nGradeSize=200\nNameSize=70\nStatSize=50\n")

    skin_manager = SkinManager()
    state = STATE_MENU
    while True:
        if state == STATE_MENU:
            if not menu_screen(screen, skin_manager): break
            state = STATE_SONG_SELECT
        elif state == STATE_SONG_SELECT:
            library = scan_song_library()
            if not library: state = STATE_MENU; continue
            audio_f, beatmap_f, mods = song_select_screen(screen, library, skin_manager)
            if audio_f is None: break
            state = STATE_PLAYING
        elif state == STATE_PLAYING:
            stats, cont = game_loop(screen, audio_f, beatmap_f, mods, skin_manager)
            if stats is None: break
            final_stats = stats
            state = STATE_RESULTS if cont else STATE_SONG_SELECT
        elif state == STATE_RESULTS:
            if results_screen(screen, final_stats, skin_manager): state = STATE_SONG_SELECT
            else: break
    pygame.quit()

if __name__ == '__main__':
    main()
