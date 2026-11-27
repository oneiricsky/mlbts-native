// The trainer panel's colours (0xRRGGBB, sRGB) and sizes. Plain C: tools/trainer_test.c checks them against WCAG 2.2
// (text at least 7:1 over the panel at its lowest opacity, even with a white picture behind; rows 24 px at 720 lines).
#pragma once

#define TR_COL_BG 0x0A140F
#define TR_COL_TEXT 0xF0F0F0
#define TR_COL_ACCENT 0xEDC254   // title, the focus ring, the mark
#define TR_COL_DIM 0xC8C8C8      // hints
#define TR_COL_BUTTON 0x1E3A2A
#define TR_COL_BUTTON_HOT 0x2A4C38
#define TR_COL_BUTTON_DOWN 0x2E5540
#define TR_ALPHA_MIN 85          // percent; the lowest TRAINER_OPACITY
#define TR_ROW_PX_1080 36        // a row's height at 1080 lines; its buttons are this square
// the panel's layout, in pixels at 1080 lines
#define TR_PANEL_W 560
#define TR_PADDING 16            // inside the panel, each side
#define TR_SPACING 10            // between items of a row
#define TR_LABEL_W 175           // where the "<" button starts, from the panel's left edge
#define TR_VALUE_W 190           // from the value's start to the ">" button
#define TR_GO_W 80
// the ratings list: name, slider, figure
#define TR_SLIDER_LABEL_W 200
#define TR_SLIDER_W 250
#define TR_VALUE_NUM_W 40
#define TR_LIST_ROWS 9           // ratings in view; the rest scroll
