# Luminote V.1.3.0

import pygame
import csv
import os
import time

# --- Constants ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
TARGET_Y = 525
WHITE = (255, 255, 255)
BLACK = (18, 18, 18)
GRAY = (40, 40, 40)

# Lane specifics
LANE_COUNT = 4
LANE_WIDTH = SCREEN_WIDTH // LANE_COUNT
LANE_KEYS = [pygame.K_d, pygame.K_f, pygame.K_j, pygame.K_k]
LANE_COLORS = [(255, 105, 180), (135, 206, 235), (255, 255, 110), (144, 238, 144)] # Pink, Blue, Yellow, Green
NOTE_RADIUS = 30
NOTE_SPEED_PPS = 500 # Pixels Per Second

# Calculated constant for timing: how long it takes for a note to travel from top to target
SCROLL_TIME_MS = (TARGET_Y / NOTE_SPEED_PPS) * 1000

# Game States
STATE_START = 0
STATE_PLAYING = 1
STATE_RESULTS = 2

# --- Classes ---
class Note(pygame.sprite.Sprite):
    def __init__(self, lane, arrival_time_ms):
        super().__init__()
        self.lane = lane
        self.arrival_time_ms = arrival_time_ms
        self.image = pygame.Surface([NOTE_RADIUS * 2, NOTE_RADIUS * 2], pygame.SRCALPHA)
        pygame.draw.circle(self.image, LANE_COLORS[self.lane], (NOTE_RADIUS, NOTE_RADIUS), NOTE_RADIUS)
        self.rect = self.image.get_rect()
        self.rect.centerx = (self.lane * LANE_WIDTH) + (LANE_WIDTH // 2)
        self.y_pos = 0.0
        self.rect.centery = int(self.y_pos)

    def update(self, dt):
        self.y_pos += NOTE_SPEED_PPS * dt
        self.rect.centery = int(self.y_pos)

class TargetReceptor(pygame.sprite.Sprite):
    def __init__(self, lane):
        super().__init__()
        self.lane = lane
        self.image = pygame.Surface([NOTE_RADIUS * 2 + 10, NOTE_RADIUS * 2 + 10], pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.rect.centerx = (self.lane * LANE_WIDTH) + (LANE_WIDTH // 2)
        self.rect.centery = TARGET_Y
        self.lit_alpha = 0
        self.draw_receptor()

    def update(self, dt):
        if self.lit_alpha > 0:
            self.lit_alpha = max(0, self.lit_alpha - (700 * dt))
            self.draw_receptor()

    def light_up(self):
        self.lit_alpha = 255
        
    def draw_receptor(self):
        self.image.fill((0,0,0,0))
        color = LANE_COLORS[self.lane]
        pygame.draw.circle(self.image, color + (self.lit_alpha,), (self.rect.width // 2, self.rect.height // 2), NOTE_RADIUS, 4)

class FeedbackText:
    def __init__(self):
        self.font = pygame.font.Font(None, 80)
        self.text = ""
        self.color = WHITE
        self.timer = 0
        self.scale = 1.0

    def set_feedback(self, text, color):
        self.text = text
        self.color = color
        self.timer = 0.5
        self.scale = 1.5

    def update(self, dt):
        if self.timer > 0:
            self.timer -= dt
            self.scale = max(1.0, self.scale - 2.0 * dt)
    
    def draw(self, surface):
        if self.timer > 0:
            scaled_font = pygame.font.Font(None, int(80 * self.scale))
            feedback_surface = scaled_font.render(self.text, True, self.color)
            alpha = min(255, 255 * (self.timer / 0.5))
            feedback_surface.set_alpha(alpha)
            x = SCREEN_WIDTH // 2 - feedback_surface.get_width() // 2
            y = 250 - feedback_surface.get_height() // 2
            surface.blit(feedback_surface, (x, y))

# --- Utility Functions ---
def load_beatmap(filename):
    beatmap = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                beatmap.append((int(row[0]), int(row[1])))
    return sorted(beatmap)

def load_high_score():
    if os.path.exists('highscore.txt'):
        with open('highscore.txt', 'r') as f: return int(f.read() or 0)
    return 0

def save_high_score(score):
    with open('highscore.txt', 'w') as f: f.write(str(score))

def calculate_grade_and_accuracy(stats):
    """Calculates final accuracy and determines the letter grade."""
    hit_counts = stats['hit_counts']
    total_notes = sum(hit_counts.values())
    if total_notes == 0:
        return 0.0, "N/A", ""

    weights = {'Perfect': 1.0, 'Good': 0.7, 'Okay': 0.35, 'Miss': 0.0}
    
    achieved_score = (hit_counts['Perfect'] * weights['Perfect'] +
                      hit_counts['Good'] * weights['Good'] +
                      hit_counts['Okay'] * weights['Okay'])
    
    max_score = total_notes * weights['Perfect']
    
    accuracy = (achieved_score / max_score) * 100

    if hit_counts['Good'] == 0 and hit_counts['Okay'] == 0 and hit_counts['Miss'] == 0:
        return 100.0, "E", "Ethereal"

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

# --- Game State Functions ---
def start_screen(screen):
    title_font = pygame.font.Font(None, 120)
    prompt_font = pygame.font.Font(None, 50)
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN: return True
                if event.key == pygame.K_ESCAPE: return False
        
        screen.fill(BLACK)
        title_text = title_font.render("Luminote", True, WHITE)
        prompt_text = prompt_font.render("Press Enter to Begin", True, WHITE)
        
        screen.blit(title_text, (SCREEN_WIDTH // 2 - title_text.get_width() // 2, 200))
        screen.blit(prompt_text, (SCREEN_WIDTH // 2 - prompt_text.get_width() // 2, 350))
        
        pygame.display.flip()

def results_screen(screen, stats):
    grade_font = pygame.font.Font(None, 250)
    grade_name_font = pygame.font.Font(None, 80)
    stat_font = pygame.font.Font(None, 50)
    prompt_font = pygame.font.Font(None, 40)
    
    accuracy, grade, grade_name = calculate_grade_and_accuracy(stats)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN: return True
                if event.key == pygame.K_ESCAPE: return False

        screen.fill(BLACK)

        grade_text = grade_font.render(grade, True, WHITE)
        screen.blit(grade_text, (SCREEN_WIDTH // 2 - grade_text.get_width() // 2, 50))
        
        grade_name_text = grade_name_font.render(grade_name, True, LANE_COLORS[1])
        screen.blit(grade_name_text, (SCREEN_WIDTH // 2 - grade_name_text.get_width() // 2, 250))

        accuracy_display = f"Accuracy: {accuracy:.2f}%"
        acc_text = stat_font.render(accuracy_display, True, WHITE)
        screen.blit(acc_text, (450, 350))

        score_text = stat_font.render(f"Score: {stats['score']}", True, WHITE)
        screen.blit(score_text, (450, 400))
        
        combo_text = stat_font.render(f"Max Combo: {stats['max_combo']}", True, WHITE)
        screen.blit(combo_text, (450, 450))

        y_offset = 350
        hit_colors = {'Perfect': LANE_COLORS[3], 'Good': LANE_COLORS[2], 'Okay': (180,180,180), 'Miss': LANE_COLORS[0]}
        for hit_type, count in stats['hit_counts'].items():
            hit_text = stat_font.render(f"{hit_type}: {count}", True, hit_colors[hit_type])
            screen.blit(hit_text, (100, y_offset))
            y_offset += 50
            
        prompt_text_surf = prompt_font.render("Press Enter to return to menu", True, WHITE)
        screen.blit(prompt_text_surf, (SCREEN_WIDTH//2 - prompt_text_surf.get_width()//2, 550))
        
        pygame.display.flip()

def game_loop(screen):
    all_sprites = pygame.sprite.Group()
    notes_group = pygame.sprite.Group()

    receptors = {}
    for i in range(LANE_COUNT):
        receptor = TargetReceptor(i)
        receptors[i] = receptor
        all_sprites.add(receptor)

    clock = pygame.time.Clock()
    last_time = time.time()
    feedback = FeedbackText()
    
    stats = {
        'score': 0, 'combo': 0, 'max_combo': 0, 'high_score': load_high_score(),
        'hit_counts': {'Perfect': 0, 'Good': 0, 'Okay': 0, 'Miss': 0}
    }

    beatmap = load_beatmap('song.csv')
    next_note_index = 0
    
    pygame.mixer.music.load('song.ogg')
    pygame.mixer.music.play()
    start_time = pygame.time.get_ticks()

    while True:
        current_time_sec = time.time()
        dt = current_time_sec - last_time
        last_time = current_time_sec
        current_time_ms = pygame.time.get_ticks() - start_time

        for event in pygame.event.get():
            if event.type == pygame.QUIT: return None, False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: return None, True
                if event.key in LANE_KEYS:
                    lane = LANE_KEYS.index(event.key)
                    receptors[lane].light_up()
                    
                    hit = False
                    closest_note, min_dist = None, float('inf')
                    for note in notes_group:
                        if note.lane == lane:
                            dist = abs(note.rect.centery - TARGET_Y)
                            if dist < min_dist:
                                min_dist, closest_note = dist, note
                    
                    if closest_note and min_dist < 80:
                        hit = True
                        if min_dist < 25: 
                            stats['score'] += 300 + stats['combo']
                            feedback.set_feedback("Perfect", LANE_COLORS[lane])
                            stats['hit_counts']['Perfect'] += 1
                        elif min_dist < 50:
                            stats['score'] += 200 + stats['combo']
                            feedback.set_feedback("Good", WHITE)
                            stats['hit_counts']['Good'] += 1
                        else:
                            stats['score'] += 100
                            feedback.set_feedback("Okay", (180, 180, 180))
                            stats['hit_counts']['Okay'] += 1
                        stats['combo'] += 1
                        closest_note.kill()
                    
                    if not hit:
                        if stats['combo'] > stats['max_combo']: stats['max_combo'] = stats['combo']
                        stats['combo'] = 0
        
        while next_note_index < len(beatmap) and current_time_ms >= beatmap[next_note_index][0] - SCROLL_TIME_MS:
            timestamp, lane = beatmap[next_note_index]
            new_note = Note(lane, timestamp)
            all_sprites.add(new_note)
            notes_group.add(new_note)
            next_note_index += 1

        all_sprites.update(dt)
        feedback.update(dt)

        for note in notes_group:
            if note.rect.top > SCREEN_HEIGHT:
                note.kill()
                if stats['combo'] > stats['max_combo']: stats['max_combo'] = stats['combo']
                stats['combo'] = 0
                feedback.set_feedback("Miss", (255, 80, 80))
                stats['hit_counts']['Miss'] += 1
        
        if stats['combo'] > stats['max_combo']: stats['max_combo'] = stats['combo']
        if stats['max_combo'] > stats['high_score']: stats['high_score'] = stats['max_combo']

        if next_note_index == len(beatmap) and len(notes_group) == 0:
            pygame.mixer.music.fadeout(1000)
            time.sleep(1)
            save_high_score(stats['high_score'])
            return stats, True
        
        screen.fill(BLACK)
        for i in range(1, LANE_COUNT):
            pygame.draw.line(screen, GRAY, (i * LANE_WIDTH, 0), (i * LANE_WIDTH, SCREEN_HEIGHT), 2)
        
        all_sprites.draw(screen)
        feedback.draw(screen)

        score_font = pygame.font.Font(None, 40)
        score_display = score_font.render(f"{stats['score']:08d}", True, WHITE)
        screen.blit(score_display, (10, 10))
        
        combo_display = score_font.render(f"{stats['combo']}x", True, WHITE)
        screen.blit(combo_display, (SCREEN_WIDTH // 2 - combo_display.get_width() // 2, 350))

        hs_display = score_font.render(f"Best Combo: {stats['high_score']}", True, WHITE)
        screen.blit(hs_display, (SCREEN_WIDTH - hs_display.get_width() - 10, 10))

        pygame.display.flip()
        clock.tick(144)

# --- Main Application Driver ---
def main():
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode([SCREEN_WIDTH, SCREEN_HEIGHT])
    pygame.display.set_caption("Luminote")
    
    current_state = STATE_START
    while True:
        if current_state == STATE_START:
            if start_screen(screen):
                current_state = STATE_PLAYING
            else:
                break
        
        elif current_state == STATE_PLAYING:
            stats, continue_playing = game_loop(screen)
            if not continue_playing:
                break
            else:
                final_stats = stats
                current_state = STATE_RESULTS
                
        elif current_state == STATE_RESULTS:
            if results_screen(screen, final_stats):
                current_state = STATE_START
            else:
                break
    
    pygame.quit()

if __name__ == '__main__':
    main()
      
