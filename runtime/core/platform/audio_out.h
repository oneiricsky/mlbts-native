// Host audio output: one shared-mode stream of interleaved float32 frames that a device thread pulls from a callback.
// fastball, replacing the SDL3 audio stream TotK Recomp's audio_mixer.c opens. Windows: WASAPI (audio_win32.c).
#pragma once
#include <stddef.h>
#include <stdint.h>

typedef struct AudioOut AudioOut;
// Fills `frames` frames of `channels` floats each. Runs on the output's own thread; must not block.
typedef void (*AudioPullFn)(void *user, float *out, uint32_t frames);

// Channels of the default playback device's mix format, 0 if there is none or it cannot be read.
int audio_out_default_channels(void);
// Opens the default playback device at `rate` Hz with `channels` channels (2, or 6 as FL FR C LFE BL BR) and starts
// pulling. On success *period gets the device period in frames and name the device's friendly name (UTF-8). NULL and a
// reason in err when there is no device or it cannot take the format.
AudioOut *audio_out_open(int rate, int channels, AudioPullFn pull, void *user, int *period, char *name, size_t nname,
                         char *err, size_t nerr);
// Stops the thread (the callback has returned when this does) and releases the device.
void audio_out_close(AudioOut *o);
