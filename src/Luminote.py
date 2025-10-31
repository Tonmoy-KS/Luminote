# src/Luminote.py
# Luminote V.1.4.0

import pygame
import csv
import os
import time
import json
import random
import requests # Make sure to run: pip install requests

# --- Constants & Configuration ---
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 600
TARGET_Y = 525

# Game States
STATE_START = 0
STATE_PLAYING = 1
STATE_RESULTS = 2
STATE_SETTINGS = 3
STATE_SONG_SELECT = 4
STATE_GET_NAME = 5

# Lane specifics
LANE_COUNT = 4
LANE_WIDTH = 800 // LANE_COUNT
GAME_AREA_OFFSET_X = (SCREEN_WIDTH - (LANE_WIDTH * LANE_COUNT)) // 2
LANE_KEYS = [pygame.K_d, pygame.K_f, pygame.K_j, pygame.K_k]
NOTE_RADIUS = 30

# Dynamic Speed & Difficulty
NOTE_BASE_SPEED_PPS = 450
game_speed_multiplier = 1.0
TIMING_WINDOWS = {'perfect': 25, 'good': 50, 'okay': 85}

# Calculated constant for timing
def get_scroll_time_ms():
    speed_pps = NOTE_BASE_SPEED_PPS * game_speed_multiplier
    if speed_pps == 0: return float('inf')
    return (TARGET_Y / speed_pps) * 1000

# API URL for Leaderboards
LEADERBOARD_API_URL = "http://127.0.0.1:5000"

# --- Theme and Settings Management ---
class ThemeManager:
    def __init__(self):
        try:
            with open('themes.json', 'r') as f: self.themes = json.load(f)
        except FileNotFoundError:
            self.themes = { "Luminote Default": { "background": [18, 18, 18], "grid_lines": [40, 40, 40], "text_main": [255, 255, 255], "text_score": [255, 255, 255], "lanes": [[255, 105, 180], [135, 206, 235], [255, 255, 110], [144, 238, 144]] } }
            with open('themes.json', 'w') as f: json.dump(self.themes, f, indent=2)
        self.current_theme_name = "Luminote Default"
        self.current_theme = self.themes[self.current_theme_name]

    def set_theme(self, theme_name):
        if theme_name in self.themes:
            self.current_theme_name = theme_name
            self.current_theme = self.themes[theme_name]

theme_manager = ThemeManager()

def load_settings():
    if os.path.exists('settings.json'):
        with open('settings.json', 'r') as f:
            settings = json.load(f)
            theme_manager.set_theme(settings.get("theme", "Luminote Default"))
    else: save_settings()

def save_settings():
    with open('settings.json', 'w') as f:
        json.dump({"theme": theme_manager.current_theme_name}, f)

# --- Classes ---
class Particle(pygame.sprite.Sprite):
    def __init__(self, x, y, color):
        super().__init__()
        self.x, self.y = x, y
        self.color = color + (255,)
        self.vx = random.uniform(-250, 250)
        self.vy = random.uniform(-450, -150)
        self.lifespan = random.uniform(0.4, 0.7)
        self.start_life = self.lifespan
        self.radius = random.uniform(3, 8)

    def update(self, dt):
        self.lifespan -= dt
        if self.lifespan <= 0: self.kill()
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 800 * dt

    def draw(self, surface):
        if self.lifespan > 0:
            alpha = max(0, int(255 * (self.lifespan / self.start_life)))
            temp_surf = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp_surf, self.color[:3] + (alpha,), (self.radius, self.radius), self.radius)
            surface.blit(temp_surf, (self.x - self.radius, self.y - self.radius))

class Note(pygame.sprite.Sprite):
    def __init__(self, lane, arrival_time_ms, note_type=0, duration_ms=0):
        super().__init__()
        self.lane = lane; self.arrival_time_ms = arrival_time_ms; self.note_type = note_type; self.duration_ms = duration_ms; self.is_held = False
        speed_pps = NOTE_BASE_SPEED_PPS * game_speed_multiplier
        self.hold_length_px = max(0, (self.duration_ms / 1000) * speed_pps)
        height = self.hold_length_px + NOTE_RADIUS * 2
        self.image = pygame.Surface([NOTE_RADIUS * 2, height], pygame.SRCALPHA)
        self.rect = self.image.get_rect(); self.rect.centerx = GAME_AREA_OFFSET_X + (self.lane * LANE_WIDTH) + (LANE_WIDTH // 2)
        self.y_pos = 0.0 - self.hold_length_px
        self.rect.y = int(self.y_pos)
        self.draw_note()

    def draw_note(self):
        color = theme_manager.current_theme['lanes'][self.lane]; head_y = self.hold_length_px + NOTE_RADIUS
        if self.note_type == 2: pygame.draw.circle(self.image, (150, 0, 0), (NOTE_RADIUS, head_y), NOTE_RADIUS)
        elif self.note_type == 1:
            pygame.draw.rect(self.image, color, (NOTE_RADIUS - 15, 0, 30, self.hold_length_px + NOTE_RADIUS))
            pygame.draw.circle(self.image, (255,255,255), (NOTE_RADIUS, head_y), NOTE_RADIUS, 5)
        else: pygame.draw.circle(self.image, color, (NOTE_RADIUS, head_y), NOTE_RADIUS)

    def update(self, dt):
        speed_pps = NOTE_BASE_SPEED_PPS * game_speed_multiplier; self.y_pos += speed_pps * dt; self.rect.y = int(self.y_pos)

class TargetReceptor(pygame.sprite.Sprite):
    def __init__(self, lane):
        super().__init__(); self.lane = lane
        self.image = pygame.Surface([NOTE_RADIUS * 2 + 10, NOTE_RADIUS * 2 + 10], pygame.SRCALPHA)
        self.rect = self.image.get_rect(); self.rect.centerx = GAME_AREA_OFFSET_X + (self.lane * LANE_WIDTH) + (LANE_WIDTH // 2); self.rect.centery = TARGET_Y
        self.lit_alpha = 0; self.draw_receptor()

    def update(self, dt):
        if self.lit_alpha > 0: self.lit_alpha = max(0, self.lit_alpha - (800 * dt)); self.draw_receptor()
    def light_up(self): self.lit_alpha = 255
    def draw_receptor(self):
        self.image.fill((0,0,0,0)); color = theme_manager.current_theme['lanes'][self.lane]
        pygame.draw.circle(self.image, color + (int(self.lit_alpha),), (self.rect.width // 2, self.rect.height // 2), NOTE_RADIUS, 4)

class FeedbackText:
    def __init__(self):
        self.font = pygame.font.Font(None, 80); self.text, self.color, self.timer, self.scale = "", (0,0,0), 0, 1.0
    def set_feedback(self, text, color): self.text, self.color, self.timer, self.scale = text, color, 0.5, 1.5
    def update(self, dt):
        if self.timer > 0: self.timer -= dt; self.scale = max(1.0, self.scale - 2.5 * dt)
    def draw(self, surface):
        if self.timer > 0:
            scaled_font = pygame.font.Font(None, int(80 * self.scale)); feedback_surface = scaled_font.render(self.text, True, self.color)
            alpha = min(255, 255 * (self.timer / 0.5)); feedback_surface.set_alpha(alpha)
            x = GAME_AREA_OFFSET_X + (LANE_WIDTH * LANE_COUNT) // 2 - feedback_surface.get_width() // 2; y = 250 - feedback_surface.get_height() // 2
            surface.blit(feedback_surface, (x, y))

# --- Utility Functions ---
def scan_for_songs():
    song_list = []
    songs_dir = 'songs'
    if not os.path.exists(songs_dir): return []
    for folder_name in os.listdir(songs_dir):
        song_path = os.path.join(songs_dir, folder_name)
        if os.path.isdir(song_path):
            meta_path = os.path.join(song_path, 'metadata.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                    song_list.append({'path': song_path, 'id': folder_name, 'title': meta.get('title', folder_name), 'artist': meta.get('artist', 'Unknown Artist')})
    return song_list

def load_beatmap(filename):
    beatmap = []
    try:
        with open(filename, 'r') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if len(row) >= 2:
                    try: beatmap.append({'time': int(row[0]), 'lane': int(row[1]), 'type': int(row[2]) if len(row) > 2 else 0, 'duration': int(row[3]) if len(row) > 3 else 0})
                    except (ValueError, IndexError): print(f"Warning: Malformed row {i+1} in {filename}. Skipping.")
        return sorted(beatmap, key=lambda x: x['time'])
    except FileNotFoundError: return []

def load_high_score():
    if os.path.exists('highscore.txt'):
        with open('highscore.txt', 'r') as f: return int(f.read() or 0)
    return 0
def save_high_score(score):
    with open('highscore.txt', 'w') as f: f.write(str(score))

def calculate_grade_and_accuracy(stats):
    hit_counts = stats['hit_counts']
    total_notes = sum(v for k, v in hit_counts.items() if k != 'Bomb Hit')
    if total_notes == 0: return 0.0, "N/A", ""
    weights = {'Perfect': 1.0, 'Good': 0.7, 'Okay': 0.35, 'Miss': 0.0}
    achieved_score = (hit_counts.get('Perfect', 0) * weights['Perfect'] + hit_counts.get('Good', 0) * weights['Good'] + hit_counts.get('Okay', 0) * weights['Okay'])
    max_score = total_notes * weights['Perfect']
    accuracy = (achieved_score / max_score) * 100 if max_score > 0 else 0
    if hit_counts.get('Good', 0) == 0 and hit_counts.get('Okay', 0) == 0 and hit_counts.get('Miss', 0) == 0: return 100.0, "E", "Ethereal"
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

# --- Leaderboard Functions ---
def submit_score(player_name, score, song_id):
    try: requests.post(f"{LEADERBOARD_API_URL}/submit", json={'name': player_name, 'score': score, 'song': song_id}, timeout=5)
    except requests.exceptions.RequestException: pass
def fetch_leaderboard(song_id):
    try:
        response = requests.get(f"{LEADERBOARD_API_URL}/leaderboard?song={song_id}", timeout=5)
        return response.json() if response.status_code == 200 else []
    except requests.exceptions.RequestException: return []

# --- Game State Functions ---
def start_screen(screen):
    title_font = pygame.font.Font(None, 120); prompt_font = pygame.font.Font(None, 50)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return 'quit'
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN: return 'song_select'
                if event.key == pygame.K_s: return 'settings'
                if event.key == pygame.K_ESCAPE: return 'quit'
        screen.fill(theme_manager.current_theme['background'])
        title_text = title_font.render("Luminote", True, theme_manager.current_theme['text_main'])
        prompt1_text = prompt_font.render("Press Enter to Play", True, theme_manager.current_theme['text_main'])
        prompt2_text = prompt_font.render("Press S for Settings", True, theme_manager.current_theme['text_main'])
        screen.blit(title_text, (SCREEN_WIDTH // 2 - title_text.get_width() // 2, 200))
        screen.blit(prompt1_text, (SCREEN_WIDTH // 2 - prompt1_text.get_width() // 2, 350))
        screen.blit(prompt2_text, (SCREEN_WIDTH // 2 - prompt2_text.get_width() // 2, 410))
        pygame.display.flip()

def settings_screen(screen):
    font_title = pygame.font.Font(None, 80); font_option = pygame.font.Font(None, 50)
    theme_names = list(theme_manager.themes.keys()); selected_index = theme_names.index(theme_manager.current_theme_name)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP: selected_index = (selected_index - 1) % len(theme_names); theme_manager.set_theme(theme_names[selected_index])
                elif event.key == pygame.K_DOWN: selected_index = (selected_index + 1) % len(theme_names); theme_manager.set_theme(theme_names[selected_index])
                elif event.key == pygame.K_RETURN: save_settings(); return True
                elif event.key == pygame.K_ESCAPE: load_settings(); return True
        screen.fill(theme_manager.current_theme['background'])
        title = font_title.render("Settings", True, theme_manager.current_theme['text_main'])
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 50))
        for i, name in enumerate(theme_names):
            color = theme_manager.current_theme['lanes'][1] if i == selected_index else theme_manager.current_theme['text_main']
            option = font_option.render(name, True, color); screen.blit(option, (SCREEN_WIDTH // 2 - option.get_width() // 2, 200 + i * 60))
        pygame.display.flip()

def song_select_screen(screen):
    songs = scan_for_songs()
    selected_index = 0
    font_title = pygame.font.Font(None, 80); font_song = pygame.font.Font(None, 50); font_artist = pygame.font.Font(None, 35)
    
    if not songs:
        font_msg = pygame.font.Font(None, 60)
        msg_text = font_msg.render("No songs found in 'songs' folder!", True, (255,80,80))
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: return None
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: return None
            screen.fill(theme_manager.current_theme['background'])
            screen.blit(msg_text, (SCREEN_WIDTH // 2 - msg_text.get_width() // 2, 250))
            pygame.display.flip()
            
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP: selected_index = (selected_index - 1) % len(songs)
                elif event.key == pygame.K_DOWN: selected_index = (selected_index + 1) % len(songs)
                elif event.key == pygame.K_RETURN:
                    selected_song = songs[selected_index]; return selected_song['path'], selected_song['id']
                elif event.key == pygame.K_ESCAPE: return None

        screen.fill(theme_manager.current_theme['background'])
        title_text = font_title.render("Select a Song", True, theme_manager.current_theme['text_main'])
        screen.blit(title_text, (SCREEN_WIDTH // 2 - title_text.get_width() // 2, 50))

        visible_songs_count = 7
        start_index = max(0, selected_index - (visible_songs_count // 2))
        end_index = min(len(songs), start_index + visible_songs_count)
        
        for i, song in enumerate(songs[start_index:end_index]):
            is_selected = (start_index + i) == selected_index
            color_title = theme_manager.current_theme['lanes'][1] if is_selected else theme_manager.current_theme['text_main']
            color_artist = theme_manager.current_theme['lanes'][2] if is_selected else (180,180,180)

            song_text = font_song.render(song['title'], True, color_title)
            artist_text = font_artist.render(song['artist'], True, color_artist)
            
            y_pos = 150 + i * 60
            screen.blit(song_text, (SCREEN_WIDTH // 2 - song_text.get_width() // 2, y_pos))
            screen.blit(artist_text, (SCREEN_WIDTH // 2 - artist_text.get_width() // 2, y_pos + 35))

        pygame.display.flip()

def get_name_screen(screen):
    font = pygame.font.Font(None, 60); name = ""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and name: return name
                elif event.key == pygame.K_BACKSPACE: name = name[:-1]
                elif len(name) < 12 and event.unicode.isprintable(): name += event.unicode
        screen.fill(theme_manager.current_theme['background'])
        prompt_text = font.render("Enter Name for Leaderboard:", True, theme_manager.current_theme['text_main'])
        name_text = font.render(name, True, theme_manager.current_theme['lanes'][1])
        pygame.draw.rect(screen, theme_manager.current_theme['grid_lines'], (SCREEN_WIDTH//2 - 200, 290, 400, 60), 2)
        screen.blit(prompt_text, (SCREEN_WIDTH // 2 - prompt_text.get_width() // 2, 200))
        screen.blit(name_text, (SCREEN_WIDTH // 2 - name_text.get_width() // 2, 300))
        pygame.display.flip()

def results_screen(screen, stats, song_id, sfx):
    sfx['results_music'].play(loops=-1); leaderboard_scores = fetch_leaderboard(song_id)
    # Highlight player's new score if they submitted one
    if 'player_name' in stats:
        player_score_entry = {'name': stats['player_name'], 'score': stats['score'], 'is_player': True}
        leaderboard_scores.append(player_score_entry)
        leaderboard_scores = sorted(leaderboard_scores, key=lambda x: x['score'], reverse=True)
    
    grade_font = pygame.font.Font(None, 250); grade_name_font = pygame.font.Font(None, 80); stat_font = pygame.font.Font(None, 45); leaderboard_font = pygame.font.Font(None, 36)
    accuracy, grade, grade_name = calculate_grade_and_accuracy(stats)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN and event.key in [pygame.K_RETURN, pygame.K_ESCAPE]: sfx['results_music'].stop(); return True
        screen.fill(theme_manager.current_theme['background'])
        grade_text = grade_font.render(grade, True, theme_manager.current_theme['text_main']); screen.blit(grade_text, (GAME_AREA_OFFSET_X + 400 - grade_text.get_width()//2, 50))
        grade_name_text = grade_name_font.render(grade_name, True, theme_manager.current_theme['lanes'][1]); screen.blit(grade_name_text, (GAME_AREA_OFFSET_X + 400 - grade_name_text.get_width()//2, 250))
        hit_colors = {'Perfect': theme_manager.current_theme['lanes'][3], 'Good': theme_manager.current_theme['lanes'][2], 'Okay': (180,180,180), 'Miss': theme_manager.current_theme['lanes'][0], 'Bomb Hit': (150,0,0)}
        y_offset = 100
        for hit_type, count in stats['hit_counts'].items():
            if count > 0: text = stat_font.render(f"{hit_type}: {count}", True, hit_colors.get(hit_type, (255,255,255))); screen.blit(text, (20, y_offset)); y_offset += 50
        y_offset += 20
        stat_items = [f"Accuracy: {accuracy:.2f}%", f"Score: {stats['score']:,}", f"Max Combo: {stats['max_combo']}"]
        for item in stat_items: text = stat_font.render(item, True, theme_manager.current_theme['text_main']); screen.blit(text, (20, y_offset)); y_offset += 50
        leaderboard_title = stat_font.render(f"{song_id} - Leaderboard", True, theme_manager.current_theme['text_main']); screen.blit(leaderboard_title, (SCREEN_WIDTH - 380, 50))
        y_offset = 110
        for i, entry in enumerate(leaderboard_scores[:10]):
            rank = f"#{i+1}"; name, score = entry['name'], f"{entry['score']:,}"
            color = theme_manager.current_theme['lanes'][2] if entry.get('is_player', False) else theme_manager.current_theme['text_main']
            rank_surf = leaderboard_font.render(rank, True, color); name_surf = leaderboard_font.render(name, True, color); score_surf = leaderboard_font.render(score, True, color)
            screen.blit(rank_surf, (SCREEN_WIDTH - 380, y_offset)); screen.blit(name_surf, (SCREEN_WIDTH - 320, y_offset)); screen.blit(score_surf, (SCREEN_WIDTH - 20 - score_surf.get_width(), y_offset)); y_offset += 35
        pygame.display.flip()

def game_loop(screen, song_folder_path, sfx):
    all_sprites = pygame.sprite.Group(); notes_group = pygame.sprite.Group(); particles = pygame.sprite.Group()
    receptors = {i: TargetReceptor(i) for i in range(LANE_COUNT)}; all_sprites.add(*receptors.values())
    clock = pygame.time.Clock(); last_time = time.time(); feedback = FeedbackText()
    stats = {'score': 0, 'combo': 0, 'max_combo': 0, 'high_score': load_high_score(), 'hit_counts': {'Perfect': 0, 'Good': 0, 'Okay': 0, 'Miss': 0, 'Bomb Hit': 0}}
    held_lanes = [False] * LANE_COUNT; powerup_active, powerup_timer, score_multiplier = False, 0.0, 1
    beatmap = load_beatmap(os.path.join(song_folder_path, 'song.csv'))
    if not beatmap: return None, True
    try: pygame.mixer.music.load(os.path.join(song_folder_path, 'song.ogg')); pygame.mixer.music.play()
    except pygame.error: return None, True # Exit if music is missing
    start_time = pygame.time.get_ticks(); next_note_index = 0; scroll_time_ms = get_scroll_time_ms()
    running = True
    while running:
        current_time_sec = time.time(); dt = current_time_sec - last_time; last_time = current_time_sec; current_time_ms = pygame.time.get_ticks() - start_time
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return None, False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                if event.key in LANE_KEYS:
                    lane = LANE_KEYS.index(event.key); receptors[lane].light_up(); held_lanes[lane] = True; hit = False
                    for note in notes_group:
                        if note.lane == lane:
                            dist = abs((note.rect.y + note.hold_length_px + NOTE_RADIUS) - TARGET_Y)
                            if dist < TIMING_WINDOWS['okay']:
                                if note.note_type == 2: stats['combo'] = 0; feedback.set_feedback("BOMB!", (255,0,0)); stats['hit_counts']['Bomb Hit'] += 1; sfx['combo_break'].play(); note.kill(); continue
                                hit = True; note.is_held = True
                                if note.note_type == 0:
                                    if dist < TIMING_WINDOWS['perfect']:
                                        stats['hit_counts']['Perfect'] += 1; feedback.set_feedback("Perfect", theme_manager.current_theme['lanes'][lane]); sfx['perfect'].play()
                                        for _ in range(20): particles.add(Particle(receptors[lane].rect.centerx, TARGET_Y, random.choice(theme_manager.current_theme['lanes'])))
                                    elif dist < TIMING_WINDOWS['good']: stats['hit_counts']['Good'] += 1; feedback.set_feedback("Good", (255,255,255)); sfx['good'].play()
                                    else: stats['hit_counts']['Okay'] += 1; feedback.set_feedback("Okay", (180,180,180)); sfx['good'].play()
                                    stats['score'] += (300 - int(dist*2)) * score_multiplier + stats['combo']; stats['combo'] += 1; note.kill()
                    if not hit and stats['combo'] > 0: sfx['combo_break'].play(); stats['combo'] = 0
            if event.type == pygame.KEYUP and event.key in LANE_KEYS:
                lane = LANE_KEYS.index(event.key); held_lanes[lane] = False
                for note in notes_group:
                    if note.lane == lane and note.note_type == 1 and note.is_held:
                        release_dist = abs(note.rect.bottom - TARGET_Y)
                        if release_dist < TIMING_WINDOWS['okay'] * 1.5: stats['hit_counts']['Perfect'] += 1; feedback.set_feedback("Hold!", theme_manager.current_theme['lanes'][lane]); stats['score'] += 500 * score_multiplier + stats['combo']; stats['combo'] += 1
                        else: stats['hit_counts']['Miss'] += 1; feedback.set_feedback("Hold Broken", (255,80,80)); stats['combo'] = 0
                        note.kill()
        while next_note_index < len(beatmap) and current_time_ms >= beatmap[next_note_index]['time'] - scroll_time_ms:
            note_data = beatmap[next_note_index]; new_note = Note(note_data['lane'], note_data['time'], note_data['type'], note_data['duration']); all_sprites.add(new_note); notes_group.add(new_note); next_note_index += 1
        all_sprites.update(dt); feedback.update(dt); particles.update(dt)
        for note in list(notes_group):
            if note.rect.top > SCREEN_HEIGHT: note.kill();
                if note.note_type != 2:
                    if stats['combo'] > 0: sfx['combo_break'].play()
                    stats['combo'] = 0; feedback.set_feedback("Miss", (255, 80, 80)); stats['hit_counts']['Miss'] += 1
        if stats['combo'] > stats['max_combo']: stats['max_combo'] = stats['combo']
        if stats['max_combo'] > stats['high_score']: stats['high_score'] = stats['max_combo']
        if powerup_active:
            powerup_timer -= dt
            if powerup_timer <= 0: powerup_active, score_multiplier = False, 1
        elif stats['combo'] > 0 and stats['combo'] % 50 == 0: powerup_active, powerup_timer, score_multiplier = True, 5.0, 2; sfx['powerup'].play()
        if not pygame.mixer.music.get_busy() and len(notes_group) == 0: running = False
        screen.fill(theme_manager.current_theme['background']); pygame.draw.rect(screen, (0,0,0), (GAME_AREA_OFFSET_X, 0, LANE_WIDTH * LANE_COUNT, SCREEN_HEIGHT))
        for i in range(1, LANE_COUNT): pygame.draw.line(screen, theme_manager.current_theme['grid_lines'], (GAME_AREA_OFFSET_X + i * LANE_WIDTH, 0), (GAME_AREA_OFFSET_X + i * LANE_WIDTH, SCREEN_HEIGHT), 2)
        all_sprites.draw(screen); [p.draw(screen) for p in particles]; feedback.draw(screen)
        font = pygame.font.Font(None, 40)
        score_display = font.render(f"{stats['score']:08d}", True, theme_manager.current_theme['text_score']); screen.blit(score_display, (GAME_AREA_OFFSET_X + 10, 10))
        combo_display = font.render(f"{stats['combo']}x", True, theme_manager.current_theme['text_main']); screen.blit(combo_display, (GAME_AREA_OFFSET_X + (LANE_WIDTH*LANE_COUNT)//2 - combo_display.get_width()//2, 350))
        hs_display = font.render(f"Best Combo: {stats['high_score']}", True, theme_manager.current_theme['text_score']); screen.blit(hs_display, (GAME_AREA_OFFSET_X + (LANE_WIDTH*LANE_COUNT) - hs_display.get_width() - 10, 10))
        if powerup_active:
            powerup_text = font.render(f"2x SCORE! ({powerup_timer:.1f}s)", True, theme_manager.current_theme['lanes'][2])
            screen.blit(powerup_text, (GAME_AREA_OFFSET_X + (LANE_WIDTH*LANE_COUNT)//2 - powerup_text.get_width()//2, 100))
        pygame.display.flip(); clock.tick(144)
    pygame.mixer.music.stop(); save_high_score(stats['high_score']); return stats, True

# --- Main Application Driver ---
def main():
    pygame.init(); pygame.mixer.init()
    screen = pygame.display.set_mode([SCREEN_WIDTH, SCREEN_HEIGHT]); pygame.display.set_caption("Luminote"); load_settings()
    try:
        sfx = { 'perfect': pygame.mixer.Sound('sfx/hit_perfect.wav'), 'good': pygame.mixer.Sound('sfx/hit_good.wav'), 'miss': pygame.mixer.Sound('sfx/miss.wav'), 'combo_break': pygame.mixer.Sound('sfx/combo_break.wav'), 'powerup': pygame.mixer.Sound('sfx/powerup.wav'), 'results_music': pygame.mixer.Sound('sfx/results.ogg') }
        for sound in sfx.values(): sound.set_volume(0.4)
    except pygame.error as e:
        print(f"Error loading sounds: {e}. Ensure 'sfx' folder and files exist. Continuing without sound."); sfx = {k: pygame.mixer.Sound(os.devnull) for k in ['perfect', 'good', 'miss', 'combo_break', 'powerup', 'results_music']}
    current_state, final_stats, song_info = STATE_START, {}, (None, None)
    while True:
        if current_state == STATE_START:
            action = start_screen(screen)
            if action == 'song_select': current_state = STATE_SONG_SELECT
            elif action == 'settings': current_state = STATE_SETTINGS
            else: break
        elif current_state == STATE_SETTINGS:
            if not settings_screen(screen): break
            current_state = STATE_START
        elif current_state == STATE_SONG_SELECT:
            result = song_select_screen(screen)
            if result: song_info = result; current_state = STATE_PLAYING
            else: current_state = STATE_START
        elif current_state == STATE_PLAYING:
            stats, continue_playing = game_loop(screen, song_info[0], sfx)
            if not continue_playing: break
            if stats: final_stats = stats; current_state = STATE_GET_NAME
            else: current_state = STATE_SONG_SELECT
        elif current_state == STATE_GET_NAME:
            player_name = get_name_screen(screen)
            if player_name: submit_score(player_name, final_stats['score'], song_info[1]); final_stats['player_name'] = player_name
            current_state = STATE_RESULTS
        elif current_state == STATE_RESULTS:
            if not results_screen(screen, final_stats, song_info[1], sfx): break
            current_state = STATE_START
    pygame.quit()

if __name__ == '__main__':
    main()