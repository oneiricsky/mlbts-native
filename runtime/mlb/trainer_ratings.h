// The trainer's player ratings: presets for a side's batting or pitching, single values for one player, and putting the
// game's own values back. Ratings are one byte each in the player's table (known-functions.md, "Player records").
#pragma once
#include <stdint.h>

#define TR_PLAYERS 80         // ids 0..39 away, 40..79 home (the home starter was id 40)
#define TR_RATING_BYTES 0x48
#define TR_RATING_MAX 99
#define TR_RATING_MIN 10

enum { TR_BATTING, TR_PITCHING, TR_GROUPS };
enum { TR_NORMAL, TR_BEST, TR_WORST, TR_LEVELS };

typedef struct { const char *label; int off; } TrRating;
extern const TrRating tr_ratings[];   // the values that can be edited one by one
extern const int tr_rating_count;

void trainer_ratings_seen(int id, uint64_t record);        // from the hook: a player of the match and his record
// The presets are for the away and the home team, whichever the controller plays.
enum { TR_AWAY, TR_HOME };
// The energy levels and the cheats go by "mine" and "theirs" instead: the side controller 1 plays, else away and home.
enum { TR_MINE, TR_THEIRS };
void trainer_ratings_preset(int side, int group, int level);
void trainer_ratings_cycle(int side, int group);   // normal, best, worst, normal
int trainer_ratings_level(int side, int group);
void trainer_ratings_set(int id, int rating, int value);   // rating: index into tr_ratings
// name and the value in effect; 0 when this id holds no player
int trainer_ratings_player(int id, char *name, int name_size);
int trainer_ratings_value(int id, int rating);
// Once per frame, from the rules. allowed 0 (a saved mode, or the trainer off): the game's own values are put back.
void trainer_ratings_apply(int allowed);
void trainer_ratings_match_over(void);     // the players are gone; presets stay for the next match
void trainer_ratings_reset(void);          // everything forgotten, presets too
int trainer_ratings_take_dirty(void);      // 1 once after a preset changed
// trainer.txt lines "preset <side> <group> <level>"
void trainer_ratings_load_line(const char *line);
void trainer_ratings_save(void *file);     // a FILE *
