import sys
import os
import struct
import time
import numpy as np

from PIL import Image

default_big_alpha = False
map_definitions = {} # key = str map_name, value = bool big_alpha
failed_adts_names = []

def parse_c_strings(data: bytes, encoding='utf-8') -> list[str]:
    """Parse null-terminated strings from raw byte data."""
    raw_strings = data.split(b'\x00')
    strings = [s.decode(encoding) for s in raw_strings if s]
    return strings

def normalize_alpha(v):
    return (v & 0xF) | ((v & 0xF) << 4)

def read_wdt_file(filepath):
    print(f"\n--- Reading: {filepath} ---")
    try:
        with open(filepath, 'rb') as f:
            map_name = os.path.splitext(os.path.basename(filepath))[0] 

            # MVER
            MVER_magic = f.read(4)
            if (MVER_magic != b'REVM'):
                print("Got MVER magic as '{}', expected 'REVM'.".format(MVER_magic))
                return
            MVER_size = f.read(4)
            WDT_version = struct.unpack('I', f.read(4))[0]
            req_wdt_version = 18
            if (WDT_version != req_wdt_version):
                print("Got WDT version '{}', expected '{}'.".format(WDT_version, req_wdt_version))
                return
            
            # read chunks until we get MPHD chunk
            while True:
                magic = f.read(4)
                size = struct.unpack('I', f.read(4))[0]

                if magic == b'DHPM':
                    assert size == 32, "Got unexpected WDT MPHD size"
                    break
                else:
                    f.read(size)

            # MPHD
            flags = struct.unpack('I', f.read(4))[0]
            adt_has_big_alpha = bool(flags & 0x04)

            print(f"Map '{map_name}' definition found, uses big alpha : {adt_has_big_alpha}")

            map_definitions[map_name] = adt_has_big_alpha

    except Exception as e:
        print(f"Failed to read {filepath}: {e}")


def read_adt_file(filepath):
    print(f"\n--- Reading: {filepath} ---")
    try:
    # if True:
        with open(filepath, 'rb') as f:

            filename = os.path.splitext(os.path.basename(filepath))[0] # Azeroth_33_55
            parts = filename.split('_')  # ['Azeroth', '33', '55']
            map_name = str(parts[0])
            Adt_indexX = int(parts[1])
            Adt_indexY = int(parts[2])

            global default_big_alpha
            big_alpha = default_big_alpha
            alphamap_size = 4096 if big_alpha else 2048
            
            global map_definitions
            if map_name in map_definitions:
                print("Reading map as Big Alpha from WDT.")
                big_alpha = map_definitions.get(map_name)
            else:
                print(f"WARNING : No WDT was given for map {map_name}, using Big alpha = {big_alpha}.")
                print("You can change this by dropping a WDT file or using -bigalpha argument to force big alpha.")
            
            # MVER
            MVER_magic = f.read(4)
            if (MVER_magic != b'REVM'):
                print("Got MVER magic as '{}', expected 'REVM'.".format(MVER_magic))
                return
            MVER_size = f.read(4)
            ADT_version = struct.unpack('I', f.read(4))[0]
            req_adt_version = 18
            if (ADT_version != req_adt_version):
                print("Got ADT version '{}', expected '{}'.".format(ADT_version, req_adt_version))
                return

            # MHDR
            MHDR_magic = f.read(4)
            if (MHDR_magic != b'RDHM'):
                print("Got MHDR magic as '{}', expected 'RDHM'.".format(MHDR_magic))
                return
            mhdr_size = struct.unpack('I', f.read(4))[0] # should be 64

            MHDR_data_offset = 20 # where MHDR data starts (mhdr_flags)

            mhdr_flags = struct.unpack('I', f.read(4))[0]
            # offset are relative to MHDR_data_offset
            MCIN_offset = struct.unpack('I', f.read(4))[0]
            MTEX_offset = struct.unpack('I', f.read(4))[0]

            # read textures array
            f.seek(MHDR_data_offset + MTEX_offset)
            MTEX_magic = f.read(4)
            if (MTEX_magic != b'XETM'):
                print("Got MTEX magic as '{}', expected 'XETM'.".format(MTEX_magic))
                return
            MTEX_size = struct.unpack('I', f.read(4))[0]
            MTEX_data = f.read(MTEX_size)

            MTEX_strings = parse_c_strings(MTEX_data)

            Num_textures = len(MTEX_strings)
            print(f"ADT has {Num_textures} textures.")
            # print(MTEX_strings)

            if (Num_textures < 1):
                print("ADT has no textures, skipping.")
                return
            
            # setup alphamap images for each texture ###########
            width, height = 1024, 1024 # 64 * 16

            # images = []
            # images_pixels = []

            alphamaps_arrays = []
            # map images to memory by texture id
            for texture in MTEX_strings:
                alphamaps_arrays.append(np.full((1024, 1024), 0, dtype=np.uint8))

            # read MCIN
            f.seek(MHDR_data_offset + MCIN_offset)
            MCIN_magic = f.read(4)
            if (MCIN_magic != b'NICM'):
                print("Got MCIN magic as '{}', expected 'NICM'.".format(MCIN_magic))
                return
            MCIN_size = struct.unpack('I', f.read(4))[0] # should be 4096

            # offset+size
            mcnk_offsets: list[list[tuple[int, int]]] = [[(0, 0) for _ in range(16)] for _ in range(16)]

            for y in range(16):
                for x in range(16):
                    mcnk_offset = struct.unpack('I', f.read(4))[0]
                    mcnk_size = struct.unpack('I', f.read(4))[0]
                    f.read(8) # useless data

                    mcnk_offsets[y][x] = (mcnk_offset, mcnk_size)

            # print(mcnk_offsets)

            generate_layer_0 = True

            # read MCNKs
            for mcnk_y in range(16):
                for mcnk_x in range(16):
                    
                    # print(f"Parsing MCNK y:{mcnk_y},x:{mcnk_x}")

                    MCNK_CHUNK_offset = mcnk_offsets[mcnk_y][mcnk_x][0]
                    MCNK_CHUNK_size = mcnk_offsets[mcnk_y][mcnk_x][1]
                    f.seek(MCNK_CHUNK_offset)

                    MCNK_magic = f.read(4)
                    if (MCNK_magic != b'KNCM'):
                        print("Got MCNK magic as '{}', expected 'KNCM'.".format(MCNK_magic))
                        return
                    MCNK_size = struct.unpack('I', f.read(4))[0] # should be 4096
                        
                    assert MCNK_size == (MCNK_CHUNK_size - 8), f"MCNK size is wrong"

                    MCNK_Flags = struct.unpack('I', f.read(4))[0]
                    indexX = struct.unpack('I', f.read(4))[0]
                    indexY = struct.unpack('I', f.read(4))[0]
                    assert indexX == mcnk_x, "MCNK X index did not match loop"
                    assert indexY == mcnk_y, "MCNK Y index did not match loop"
                    num_layers = struct.unpack('I', f.read(4))[0]
                    f.read(4) # doodads
                    f.read(4) # ofsMCVT
                    f.read(4) # ofsNormals
                    offset_MCLY = struct.unpack('I', f.read(4))[0]
                    f.read(4) # ofsMCRF
                    offset_MCAL = struct.unpack('I', f.read(4))[0] #offset to magic, not data
                    size_Alpha = struct.unpack('I', f.read(4))[0] # includes chunk header(magic+size). sum of data of all layers
                    # print(size_Alpha)
                    # ...

                    do_not_fix_alpha_map = bool(MCNK_Flags & (1 << 15))
                    # if (do_not_fix_alpha_map):
                    #     print(f'MCNK has do_not_fix_alpha_map enabled')
                    
                    # MCLY
                    f.seek(MCNK_CHUNK_offset + offset_MCLY)
                    MCLY_magic = f.read(4)
                    if (MCLY_magic != b'YLCM'):
                        print("Got MCLY magic as '{}', expected 'YLCM'.".format(MCLY_magic))
                        return
                    MCLY_size = struct.unpack('I', f.read(4))[0]
                    assert num_layers == (MCLY_size / 16), f"Unexpected MCLY size or layer count"


                    y_tile_pos = 64 * indexY
                    x_tile_pos = 64 * indexX

                    layer0_tex_id = 0
                    
                    # layer0_alphamap_data = [255] * 4096 # initialize all to 255
                    layer0_alphamap_data = np.full((64, 64), 255, dtype=np.uint8)

                    f.seek(MCNK_CHUNK_offset + offset_MCLY + 8) # Skip magic + size
                    layers_data = f.read(num_layers * 16)

                    for layer_id in range(num_layers):
                        start = layer_id * 16
                        layer_entry = layers_data[start : start + 12]

                        tex_id, flags, ofsalphamap = struct.unpack('3I', layer_entry)
                        # tex_id = struct.unpack('I', f.read(4))[0]
                        # # print(tex_id)
                        # flags = struct.unpack('I', f.read(4))[0]
                        # ofsalphamap = struct.unpack('I', f.read(4))[0]
                        # f.read(4) # ground effect id

                        use_alpha_map = bool(flags & 0x100)
                        alpha_map_compressed  = bool(flags & 0x200)
                        # print(f"use alpha : {use_alpha_map}")
                        # print(f"alpha compressed : {alpha_map_compressed}")

                        # assert tex_id < Num_textures, f"Error; MCLY tex id exceeded Num_textures"

                        if layer_id == 0:
                            layer0_tex_id = tex_id
                            assert use_alpha_map == False, "Error, layer 0 should never have an alpha map" # only big alpha should be compressed
                            continue

                        ###################

                        assert use_alpha_map == True, "Error, layer id > 0 doesn't use alphamap"

                        # read alphamap (MCAL)
                        if use_alpha_map:
                            # print(f"Layer Id {layer_id}")
                            if not alpha_map_compressed:
                                assert (offset_MCAL + ofsalphamap + alphamap_size) <= (offset_MCAL + size_Alpha), f"Unexpected alphamap offset {offset_MCAL + ofsalphamap + alphamap_size} {offset_MCAL + size_Alpha} {alphamap_size} {size_Alpha}"

                            f.seek(MCNK_CHUNK_offset + offset_MCAL + ofsalphamap + 8)
                            #alphamap_data = []
                            if not big_alpha:
                                assert alpha_map_compressed == False, "Error, only big alpha can be compressed" # only big alpha should be compressed

                                raw_alphamap_data = np.frombuffer(f.read(2048), dtype=np.uint8)

                                low = ((raw_alphamap_data & 0x0F) << 4) | (raw_alphamap_data & 0x0F)
                                high = ((raw_alphamap_data & 0xF0) >> 4) | (raw_alphamap_data & 0xF0)

                                alphamap_data = np.empty(4096, dtype=np.uint8)
                                alphamap_data[0::2] = low
                                alphamap_data[1::2] = high

                                if not do_not_fix_alpha_map: # fix alpha map
                                    # for i in range(64):
                                    #     alphamap_data[i * 64 + 63] = alphamap_data[i * 64 + 62]
                                    #     alphamap_data[63 * 64 + i] = alphamap_data[62 * 64 + i]
                                    # alphamap_data[63 * 64 + 63] = alphamap_data[62 * 64 + 62]
                                    amap = amap.reshape(64, 64)
                                    amap[:, 63] = amap[:, 62]
                                    amap[63, :] = amap[62, :]
                                    amap[63, 63] = amap[62, 62]
                            else: #big alpha
                                if not alpha_map_compressed:
                                    # alphamap_data = f.read(alphamap_size)
                                    # alphamap_data = list(alphamap_data) # each byte becomes an 8-bit int
                                    alphamap_data = np.frombuffer(f.read(4096), dtype=np.uint8)
                                else: # compressed
                                    # print("Compressed alphamap!")
                                    raw_alphamap_data = []
                                    while len(raw_alphamap_data) < 4096:
                                        cmd_byte = f.read(1)
                                        if not cmd_byte:
                                            raise EOFError("Unexpected end of file while decoding alpha map")
                                        
                                        cmd = cmd_byte[0]
                                        fill_mode = (cmd & 0x80) != 0  # in the first bit of that byte (sign bit) check if it's true. When true that means we are in "fill" mode, if false, "copy" mode
                                        count = cmd & 0x7F  # the next 7 bits of the byte determine how many times we "fill" or "copy" (count) (eg, max value 127 - actually 64, see notes)

                                        if fill_mode:
                                            fill_byte = f.read(1)
                                            raw_alphamap_data.extend([fill_byte[0]] * count) # converts the byte to int
                                        else: # copy mode
                                            copy_bytes = f.read(count)
                                            raw_alphamap_data.extend(copy_bytes[i] for i in range(count))

                                    # apparently blizz alphamaps can be bugged and have more than 4096, just ignore extra bytes
                                    assert len(raw_alphamap_data) >= 4096, f"Error uncompressing alphamap, not enough  bytes {len(alphamap_data)}"

                                    alphamap_data = np.array(raw_alphamap_data, dtype=np.uint8)

                            # print(alphamap_data)

                            # if (do_not_fix_alpha_map):
                                # test alpha_map[x][63] == alpha_map[x][62]
                                # TODO
                                # assert alphamap_data[62] == alphamap_data[63], f"Error, do_not_fix_alpha_map flag but rows did not match : got {alphamap_data[62]} and {alphamap_data[63]}" 

                            # alphamap_data = alphamap_data.astype(np.int16) # for safe substraction
                            alphamap_data = alphamap_data.reshape((64, 64))

                            alphamaps_arrays[tex_id][
                                y_tile_pos : y_tile_pos + 64,
                                x_tile_pos : x_tile_pos + 64
                            ] = alphamap_data

                            # update layer 0
                            if (generate_layer_0):
                                # layer0_alphamap_data -= alphamap_data
                                layer0_alphamap_data = np.maximum(layer0_alphamap_data - alphamap_data, 0)

                                # for alpha_i in range(4096):

                                    # if (alpha_i == 23 and indexX==0 and indexY==0):
                                    #     print(alphamap_data[alpha_i]) # debug

                                    # print(layer0_alphamap_data[alpha_i])
                                    # layer0_alphamap_data[alpha_i] -= alphamap_data[alpha_i]

                                    # TODO, some bits add up to more than 255 total, investigate if it's normal or not
                                    #assert layer0_alphamap_data[alpha_i] >= 0, f"Error; got negative alpha value for layer 0 : {layer0_alphamap_data[alpha_i]} {alphamap_data[alpha_i] } index {alpha_i} in layer {layer_id}"


                    # Finally Update layer 0 texture
                    # print(f"Layer 0 tex id : {layer0_tex_id}")
                    if generate_layer_0:

                        # TODO : construct whole array in numpy instead and generate once
                        alphamaps_arrays[layer0_tex_id][
                            y_tile_pos : y_tile_pos + 64,
                            x_tile_pos : x_tile_pos + 64
                        ] = layer0_alphamap_data  # already 64x64

            output_root = os.path.join("output", map_name)
            # for i, img in enumerate(images):
            for i, arr in enumerate(alphamaps_arrays):
                tex_name = MTEX_strings[i]
                filename = os.path.basename(tex_name)
                basename = os.path.splitext(filename)[0]

                save_name = f"{map_name}_{Adt_indexX}_{Adt_indexY}-{basename}.png"
                # output_path = "output\\" + map_name + "\\" + save_name
                output_path = os.path.join(output_root, save_name)

                os.makedirs(output_root, exist_ok=True)
                img = Image.fromarray(arr, mode="L")
                img.save(output_path)

    except Exception as e:
        print(f"Failed to read {filepath}: {e}")
        global failed_adts_names
        filename = os.path.splitext(os.path.basename(filepath))[0]
        failed_adts_names.append(filename)


def main():
    if len(sys.argv) <= 1:
        print("No ADT file given. Drag and drop ADT/WDT files or folders onto this script to read them, or add the paths as argument.")
        return
    
    start_time = time.time()
    
    global default_big_alpha

    got_wdt = False

    files_list = []

    for arg  in sys.argv[1:]:
        # extract filepaths from folders
        if os.path.isdir(arg):
            for root, dirs, files in os.walk(arg):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    files_list.append(filepath)

        elif arg == "-bigalpha":
            default_big_alpha = True
        else:
            files_list.append(arg)
    
    if default_big_alpha:
        print("Command [-bigalpha] given, big alpha will be used as default.")
    else:
        print("Command [-bigalpha] not given, small alpha will be used as default.")

    for filepath  in files_list:
        if not filepath.lower().endswith(".wdt"):
            continue
        if os.path.isfile(filepath ):
            read_wdt_file(filepath)

    if not got_wdt:
        print("Include a WDT to specify the map's alpha format." \
        "\nIf no WDT was dropped, small alpha will be used by default, you can add the argument -bigalpha to default to big alpha instead without using a WDT.")

    adt_count = 0
    for filepath  in files_list:
        if not filepath.lower().endswith(".adt"):
            print(f"Skipping non .adt file: {filepath}")
            continue

        if os.path.isfile(filepath ):
            read_adt_file(filepath )
            adt_count += 1
        else:
            print(f"Not a valid file: {filepath }")

    end_time = time.time()
    elapsed = end_time - start_time

    print(f"Processed {adt_count} ADTs in {elapsed:.2f} seconds.")
    global failed_adts_names
    failed_adts_count = len(failed_adts_names)
    if failed_adts_count > 0:
        print(f"Failed to process {failed_adts_count} ADTs:")
        print(failed_adts_names)

    input("Press Enter to exit...")
    

if __name__ == "__main__":
    main()

    