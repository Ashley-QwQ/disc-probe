#!/usr/bin/env python

import sys
import json
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor

command_path = Path.cwd().resolve()
script_path = Path(__file__).resolve().parent

defaults = {
    "map_path": Path(script_path, "image_texture_maps", "10-angle.json"),
}


def get_relative_path(input_path, relative_to_path):
    input_path = input_path.resolve()
    relative_to_path = relative_to_path.resolve()
    
    try:
        relative_path = input_path.relative_to(relative_to_path)
    except ValueError:
        relative_path = input_path
    
    return relative_path


def parse_args(args):
    parser = argparse.ArgumentParser(
        description=f"Turns an image into a numpy array, for textured burning.\n\n"
                    f"Default parameters are shown in [brackets].",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-i", "--image", dest="image_path", type=str, required=True,
                        help=f"the input image file, must be 6000 x 6000 pixels"
                       )
    relative_default_map_path = get_relative_path(defaults["map_path"], command_path)
    parser.add_argument("-m", "--map", dest="map_path", type=str, required=False, default=defaults["map_path"],
                        help=f"the texture map file to use [\"{relative_default_map_path}\"]"
                       )
    
    parsed_args = parser.parse_args(args)
    
    # Interpret string arguments
    image_path = Path(parsed_args.image_path).resolve()
    if not image_path.is_file():
        parser.error(f"the input image file \"{parsed_args.image_path}\" does not exist")
    parsed_args.image_path = image_path
    
    img = Image.open(parsed_args.image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.size != (6000, 6000):
        parser.error(f"the input image must be exactly 6000 x 6000 pixels, but it is {img.size[0]} x {img.size[1]} pixels")
    parsed_args.img = img
    
    output_file = parsed_args.image_path.with_suffix(".npy")
    if output_file.is_file():
        output_file.unlink()
    parsed_args.output_path = output_file
    
    map_path = Path(parsed_args.map_path).resolve()
    if not map_path.is_file():
        parser.error(f"the input map file \"{parsed_args.map_path}\" does not exist")
    parsed_args.map_path = map_path
    
    with open(parsed_args.map_path, "r", encoding="utf-8") as f:
        parsed_args.color_map = json.load(f)
    
    parsed_args.color_list = list(parsed_args.color_map.keys())
    parsed_args.texture_list = list(parsed_args.color_map.values())
    parsed_args.color_index_map = {ImageColor.getrgb(color): idx for idx, color in enumerate(parsed_args.color_list)}
    
    return parsed_args


def main(args):
    print()
    parsed_args = parse_args(args)
    
    print(f"Image to convert: \"{get_relative_path(parsed_args.image_path, command_path)}\"")
    print(f"Using {len(parsed_args.texture_list)} textues from the texture map file: \"{get_relative_path(parsed_args.map_path, command_path)}\"")
    
    print()
    print("Converting image to Numpy texture array...")
    
    arr = np.array(parsed_args.img)
    
    mapped_arr = np.full(arr.shape[:2], -1, dtype=np.int32)
    
    for color, id in parsed_args.color_index_map.items():
        mask = np.all(arr == color, axis=-1)
        mapped_arr[mask] = id
    
    used_ids = np.unique(mapped_arr)
    if -1 in used_ids:
        valid_colors_string = ", ".join(parsed_args.color_list)
        raise Exception(f"Some colors were not properly mapped! Valid colors: {valid_colors_string}")
    else:
        print("Conversion done! All colors were mapped correctly.")
    
    print()
    print("Saving Numpy array to file...")
    
    np.save(parsed_args.output_path, mapped_arr)
    
    design_path = get_relative_path(parsed_args.output_path, command_path)
    print(f"Done! Saved to: \"{design_path}\"")
    
    print()
    colors_string = ", ".join([parsed_args.color_list[x] for x in used_ids])
    textures_string = ", ".join([parsed_args.texture_list[x] for x in used_ids])
    print(f"Colors Used: {colors_string}")
    print(f"Textures Used: {textures_string}")
    
    print()
    print("Use the following command to build the ISO image:")
    
    print()
    textures_string = " ".join(parsed_args.texture_list)
    iso_path = Path("iso", design_path.with_suffix(".iso").name)
    print(f"python -m discprobe image --geo latest --design-npy {design_path} --textures {textures_string} --r-max 57.6 --output {iso_path}")

if __name__ == "__main__":
    main(sys.argv[1:])
