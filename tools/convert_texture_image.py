#!/usr/bin/env python

import sys
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor


def parse_args(args):
    parser = argparse.ArgumentParser(
        description=f"Turns an image into a numpy array, for textured burning.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-i", "--input", dest="input", type=str, required=True,
                        help=f"the input image file"
                       )
    parser.add_argument("-c", "--color", dest="use_angle", action="store_false",
                        help=f"map colors based on color order instead of refracrtion angle order"
                       )
    
    parsed_args = parser.parse_args(args)
    
    # Interpret string arguments
    input_file = Path(parsed_args.input).resolve()
    if not input_file.is_file():
        parser.error(f"the input file \"{parsed_args.input}\" does not exist")
    parsed_args.input = input_file
    
    img = Image.open(parsed_args.input)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.size != (6000, 6000):
        parser.error(f"the input image must be exactly 6000 x 6000 pixels, but it is {img.size[0]} x {img.size[1]} pixels")
    parsed_args.img = img
    
    output_file = parsed_args.input.with_suffix(".npy")
    if output_file.is_file():
        output_file.unlink()
    parsed_args.output = output_file
    
    # Interpret boolean arguments
    if parsed_args.use_angle:
        # Sorted by refraction angle
        parsed_args.color_map = {
            "#000000": '"MIX:92,87,83,8D,60"',  # Dull Gray (Neutral)
            "#FFFFFF": '0000FF',                # Iridescent / Multiple Angles (Dim)
            "#FF0000": '92',                    # Shallowest Angle (Bright)
            "#FF7F00": '929266',                # ... (Dim)
            "#FFFF00": 'B9',                    # ... (Bright)
            "#00FF00": '2AE304',                # ... (Dim)
            "#00FFFF": 'B966B9',                # ... (Bright)
            "#0000FF": '66',                    # ... (Bright)
            "#7F00FF": 'A5A566',                # ... (Bright)
            "#FF00FF": 'A5',                    # Steepest Angle (Bright)
        }
    else:
        # Sorted by refraction color
        parsed_args.color_map = {
            "#000000": '"MIX:92,87,83,8D,60"',  # Dull Gray (Neutral)
            "#FFFFFF": '0000FF',                # Iridescent / Multiple Angles (Dim)
            "#FF0000": '66',                    # Red (Bright)
            "#FF7F00": '929266',                # Orange (Dim)
            "#FFFF00": 'A5A566',                # Yellow-Green (Bright)
            "#00FF00": 'A5',                    # Green (Bright)
            "#00FFFF": '2AE304',                # Cyan (Dim)
            "#0000FF": '92',                    # Green-Blue (Bright)
            "#7F00FF": 'B9',                    # Blue (Bright)
            "#FF00FF": 'B966B9',                # Violet (Bright)
        }
    parsed_args.color_list = list(parsed_args.color_map.keys())
    parsed_args.texture_list = list(parsed_args.color_map.values())
    parsed_args.color_index_map = {ImageColor.getrgb(color): idx for idx, color in enumerate(parsed_args.color_list)}
    
    return parsed_args


def main(args):
    print()
    parsed_args = parse_args(args)
    
    print("NOTE: ", end="")
    if parsed_args.use_angle:
        print("Image colors will be mapped in order of refraction angle.")
    else:
        print("Image colors will be mapped in order of refraction color.")
    
    print()
    print("Converting image to Numpy texture array...")
    
    arr = np.array(parsed_args.img)
    
    mapped_arr = np.full(arr.shape[:2], -1, dtype=np.int32)
    
    for color, id in parsed_args.color_index_map.items():
        mask = np.all(arr == color, axis=-1)
        mapped_arr[mask] = id
    
    used_ids = np.unique(mapped_arr)
    if -1 in used_ids:
        raise Exception(f"Some colors were not properly mapped! Valid colors: {", ".join(parsed_args.color_list)}")
    
    print("Saving Numpy array to file...")
    
    np.save(parsed_args.output, mapped_arr)
    
    print(f"Done! Saved to: \"{parsed_args.output}\"")
    print()
    print(f"Colors Used: {", ".join([parsed_args.color_list[x] for x in used_ids])}")
    print(f"Textures Used: {", ".join([parsed_args.texture_list[x] for x in used_ids])}")
    print()
    print("Use the following command to build the ISO image:")
    
    design_path = parsed_args.output.relative_to(Path.cwd())
    textures_string = " ".join(parsed_args.texture_list)
    iso_path = Path("iso").joinpath(design_path.with_suffix(".iso").name)
    print()
    print(f"python -m discprobe image --geo latest --design-npy {design_path} --textures {textures_string} --r-max 57.6 --output {iso_path}")
    

if __name__ == "__main__":
    main(sys.argv[1:])
