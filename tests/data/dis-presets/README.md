# DIS interchange fixtures

51 mock files. Built-in values come from the read-only DIS checkout at `619ec75`;
community values come from `D:/disc-probe/data/community-calibrations/dis-github.json` (174 entries, collected 2026-11-10).
Variants are synthetic edge cases, not new measurements. DVD±R and CD-R examples retain source names.
Old schemas are the schema 2/3 formats still supported at v1.5.0 (`29b8cc1`); schema 4 also already existed in that release.
Regenerate with `python tools/build_dis_preset_fixtures.py` when those local sources exist.

| File | Expected | Coverage | Source |
|---|---|---|---|
| 01-builtin-cd-0.json | parse | Source-exact built-in entry cd-80 | 619ec75:cdPresets[0] |
| 02-builtin-cd-1.json | parse | Source-exact built-in entry ritek-medical-aqua | 619ec75:cdPresets[1] |
| 03-builtin-cd-2.json | parse | Source-exact built-in entry verbatim-azo-43438 | 619ec75:cdPresets[2] |
| 04-builtin-cd-3.json | parse | Source-exact built-in entry cd-74 | 619ec75:cdPresets[3] |
| 05-builtin-dvd-0.json | parse | Source-exact built-in entry dvd-5-120mm | 619ec75:dvdPresets[0] |
| 06-builtin-dvd-1.json | parse | Source-exact built-in entry verbatim-dvd-r-azo-43533 | 619ec75:dvdPresets[1] |
| 07-builtin-dvd-2.json | parse | Source-exact built-in entry verbatim-dvd-r-azo-43523 | 619ec75:dvdPresets[2] |
| 08-builtin-dvd-3.json | parse | Source-exact built-in entry verbatim-dvd-plus-r-azo-43498 | 619ec75:dvdPresets[3] |
| 09-builtin-dvd-4.json | parse | Source-exact built-in entry philips-dvd-plus-r | 619ec75:dvdPresets[4] |
| 10-builtin-dvd-5.json | parse | Source-exact built-in entry ritek-dvd-plus-r-e-series | 619ec75:dvdPresets[5] |
| 11-builtin-bd-0.json | parse | Source-exact built-in entry bd-r-sl-25gb | 619ec75:bluRayPresets[0] |
| 12-builtin-bd-1.json | parse | Source-exact built-in entry bd-r-ritek-10x | 619ec75:bluRayPresets[1] |
| 13-builtin-bd-2.json | parse | Source-exact built-in entry bd-r-ritek-12x | 619ec75:bluRayPresets[2] |
| 14-builtin-bd-3.json | parse | Source-exact built-in entry bd-r-verbatim-64099 | 619ec75:bluRayPresets[3] |
| 15-community-0.json | parse | Posted fields retained; calibration unverified | D169-1 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169 |
| 16-community-1.json | refuse | Incomplete posted parameters: missing sector count refused without inventing capacity | D169-2 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169#discussioncomment-19475320 |
| 17-community-2.json | refuse | Incomplete posted parameters: missing sector count refused without inventing capacity | D169-3 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/169#discussioncomment-19523418 |
| 18-community-3.json | parse | Posted fields retained; calibration unverified | D275-1 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/275 |
| 19-community-4.json | refuse | Incomplete posted parameters: missing sector count refused without inventing capacity | D172-2 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/172#discussioncomment-19494863 |
| 20-community-5.json | refuse | Incomplete posted parameters: missing sector count refused without inventing capacity | D172-3 https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/172#discussioncomment-19471847 |
| 21-chinese-name.json | parse | Chinese custom name | 619ec75:dvd-5-120mm, synthetic mutation |
| 22-emoji-name.json | parse | Path-like id, emoji and HTML text stay data | 619ec75:dvd-5-120mm, synthetic mutation |
| 23-mid-present.json | parse | Nonstandard MID extension retained, DIS install refused | 619ec75:dvd-5-120mm, synthetic mutation |
| 24-mid-absent.json | parse | MID stays unknown | 619ec75:dvd-5-120mm, synthetic mutation |
| 25-pitch-absent.json | parse | Missing coefficients default to zero | 619ec75:dvd-5-120mm, synthetic mutation |
| 26-pitch-zero.json | parse | Explicit zeros preserved | 619ec75:dvd-5-120mm, synthetic mutation |
| 27-pitch-linear.json | parse | Positive variable pitch; bounded DP angle conversion | 619ec75:dvd-5-120mm, synthetic mutation |
| 28-pitch-cubic.json | parse | Cubic pitch model | 619ec75:dvd-5-120mm, synthetic mutation |
| 29-dvd-odd-sectors.json | parse | DIS permits odd DVD geometry capacity | 619ec75:dvd-5-120mm, synthetic mutation |
| 30-cd-rw.json | parse | CD-RW and odd CD capacity | 619ec75:cd-80, synthetic mutation |
| 31-dvd-plus-rw.json | parse | Rewritable DVD+RW label | 619ec75:dvd-5-120mm, synthetic mutation |
| 32-dvd-minus-rw.json | parse | DVD-RW label | 619ec75:dvd-5-120mm, synthetic mutation |
| 33-unknown-field.json | parse | Unknown future field preserved, geometry/install refused | 619ec75:dvd-5-120mm, synthetic mutation |
| 34-resource-null.json | parse | Nullable optional resource/contributor | 619ec75:dvd-5-120mm, synthetic mutation |
| 35-cd-legacy-speed.json | parse | Stored compatibility speed retained; generation fixed at 1200 | 619ec75:cd-80, synthetic mutation |
| 36-dvd-legacy-bit.json | parse | Stored compatibility bit length retained; generation fixed at 133.3 | 619ec75:dvd-5-120mm, synthetic mutation |
| 37-bd-pitch.json | parse | BD variable pitch and polarity | 619ec75:bd-r-sl-25gb, synthetic mutation |
| 38-single-preset.json | parse | One standalone DVD preset | 619ec75:dvdPresets[0] |
| 39-dp-wrapper.json | parse | Existing DP export wrapper | 619ec75:cdPresets[0] |
| 40-schema-2.json | parse | Old schema supported by v1.5.0 and current reader | 29b8cc1:DiscPresetJsonStore schema 2 |
| 41-schema-3.json | parse | Interim schema missing compatibility speed | 29b8cc1:DiscPresetJsonStore schema 3 |
| 42-duplicate-ids.json | parse | Duplicate ids reported; index selection; never overwrite | 619ec75:dvdPresets[0], synthetic duplicate |
| 43-disabled.json | parse | Disabled entry is unchecked by default | 619ec75:cdPresets[0] |
| 44-whole-catalog.json | parse | Whole catalog, all three media and resource keys | 619ec75:built-in-disc-presets.json |
| 45-bad-json.json | refuse | Truncated JSON is refused | synthetic broken JSON |
| 46-wrong-type.json | refuse | String radius refused | 619ec75:dvd-5-120mm, synthetic mutation |
| 47-negative-radius.json | refuse | Out-of-range radius refused | 619ec75:dvd-5-120mm, synthetic mutation |
| 48-bad-pitch.json | refuse | Nonpositive pitch inside interval refused | 619ec75:dvd-5-120mm, synthetic mutation |
| 49-bd-odd.json | refuse | BD must be 32-sector aligned | 619ec75:bd-r-sl-25gb, synthetic mutation |
| 50-future-schema.json | refuse | Unknown schema refused without guessing geometry | synthetic schema |
| 51-unwrapped-over360.json | archive | pitchLinear=1e8: corrected unwrapped error >360 degrees; image use refused | synthetic mutation of 27-pitch-linear.json |
