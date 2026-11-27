New-work page art (opened from the lobby's drive) - 2026-11-10
=================================================================
Look: same as the lobby and the burner page: flat toon fill, image-space outlines, the warm lamp pool baked in
(render_desk.py's pool gains: subtle on paper, strong and warm on dark). Everything is shot straight down with an
orthographic camera; the paper and the envelope lie flat and are shot from above too.

out/ (final, paper + dark):
  top_<theme>.png             2560 x 1440, opaque. The app's burner model (same mesh as burner_*.png, read from
                              D:\disc-video\pack\disc_explode_render.blend, never saved) from directly above, tray out
                              200 mm, a printable disc on it (label side up) with a LOW-KEY DP mark printed along the upper
                              half of the label ring: the two letters each lie flat (not bent), each turned so its top
                              faces away from the disc centre where it sits (38 to 54 mm radius), in a tone ~10 % darker (paper) / ~10 % lighter (dark) than the
                              label, the P's half-disc bowl keeping a hint of its rainbow hue (mark_soft_{D,P}_<theme>.png +
                              mark_split.json from make_mark.py, keyed from art/wordmark/dp-halfdisc-<theme>.jpg); a decal without outlines,
                              under the same pool as the disc. Drive centred at 20 % of the width,
                              tray front at 78 % of the height, the body runs off the top (zoomed in). Pool centred at
                              47 % / 45 %, falling across the drive and the right half; soft shadow down-left (lamp up
                              right). Right of x = 833 px is plain lit desk for the form.
  paper_<theme>.png           1400 x 1700, transparent outside the sheet; fine paper grain; same pool, brighter on
                              the left (toward the pool centre).
  paper_shadow_<theme>.png    same canvas, the sheet's soft drop shadow (offset down-left) on its own layer.
  envelope_back_<theme>.png   1600 x 1541: back panel (its inside shows above the pocket) + the flap opened up.
  envelope_front_<theme>.png  same canvas: front pocket with a thumb notch, button, string wound round it, loose end.
                              Draw back -> sliding sheet -> front.
  top.json / paper.json / envelope.json   placement (px, origin top-left):
      top: disc centre + radius, label ring radii, hole, the printed mark's rect; drive body and tray rects; pool centre and sigma.
      paper: sheet rect, content rect, inner margins (8 % / 6.5 %).
      envelope: pocket top y (the slot), back top, flap top, envelope rect, button centre.
  check_*.png                 local check pictures only (not for the page).

The DP mark IS rendered on the disc (top.json mark_letters, mark_rect_px). Size / place / spacing: MARK_R0,
MARK_H, MARK_TRACK in render_newplan.py; contrast and the bowl's hue: make_mark.py (the 0.90 / 1.12 factors and the 0.30 hue amount).

Re-render (local Git Bash):  bash run_newplan.sh "top paper envelope"      (about 2 min; --preview = quick, ss 1)
Script: render_newplan.py (modes top / paper / envelope). check_compose.py makes the check pictures.
