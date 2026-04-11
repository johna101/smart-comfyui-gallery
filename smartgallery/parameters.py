# Smart Gallery for ComfyUI - Generation Parameters Data Dictionary
# Central registry of known ComfyUI/A1111 generation parameters.
# Defines types, display names, and core/extended grouping for consistent UI rendering.

import re

# ---------------------------------------------------------------------------
# DATA DICTIONARY — known generation parameters
# ---------------------------------------------------------------------------
# type: 'int', 'float', 'str', 'hash', 'size'
# group: 'core' (always visible), 'extended' (toggle to show)

GENERATION_PARAMS = {
    # Core — most influential on output, always displayed
    # Order: Model, Sampler, Scheduler, CFG, Steps, Seed, Size
    'Model':              {'type': 'str',   'display': 'Model',     'group': 'core', 'order': 0},
    'Sampler':            {'type': 'str',   'display': 'Sampler',   'group': 'core', 'order': 1},
    'Schedule type':      {'type': 'str',   'display': 'Scheduler', 'group': 'core', 'order': 2},
    'Scheduler':          {'type': 'str',   'display': 'Scheduler', 'group': 'core', 'order': 2},
    'scheduler_name':     {'type': 'str',   'display': 'Scheduler', 'group': 'core', 'order': 2},
    'CFG scale':          {'type': 'float', 'display': 'CFG',       'group': 'core', 'order': 3},
    'Steps':              {'type': 'int',   'display': 'Steps',     'group': 'core', 'order': 4},
    'Seed':               {'type': 'int',   'display': 'Seed',      'group': 'core', 'order': 5},
    'Size':               {'type': 'size',  'display': 'Size',      'group': 'core', 'order': 6},

    # Extended — secondary metadata, shown on toggle
    'Model hash':         {'type': 'hash',  'display': 'Model Hash',  'group': 'extended'},
    'VAE':                {'type': 'str',   'display': 'VAE',         'group': 'extended'},
    'VAE hash':           {'type': 'hash',  'display': 'VAE Hash',    'group': 'extended'},
    'Clip skip':          {'type': 'int',   'display': 'Clip Skip',   'group': 'extended'},
    'Denoising strength': {'type': 'float', 'display': 'Denoise',     'group': 'extended'},
    'Hires upscale':      {'type': 'float', 'display': 'Hires Scale', 'group': 'extended'},
    'Hires steps':        {'type': 'int',   'display': 'Hires Steps', 'group': 'extended'},
    'Hires upscaler':     {'type': 'str',   'display': 'Upscaler',    'group': 'extended'},
    'Version':            {'type': 'str',   'display': 'Version',     'group': 'extended'},
    'Token merging ratio': {'type': 'float', 'display': 'Token Merge', 'group': 'extended'},
    'RNG':                {'type': 'str',   'display': 'RNG',         'group': 'extended'},
    'Face restoration':   {'type': 'str',   'display': 'Face Restore', 'group': 'extended'},
    'Eta':                {'type': 'float', 'display': 'Eta',         'group': 'extended'},
    'ENSD':               {'type': 'int',   'display': 'ENSD',        'group': 'extended'},
    'Lora hashes':        {'type': 'str',   'display': 'LoRA Hashes', 'group': 'extended'},
    'TI hashes':          {'type': 'str',   'display': 'TI Hashes',   'group': 'extended'},
}


def cast_param(key, raw_value):
    """
    Look up a parameter key in the dictionary, cast to correct type,
    return a structured dict for the frontend.
    Unknown keys default to string type, extended group.
    """
    raw_value = raw_value.strip()
    entry = GENERATION_PARAMS.get(key)

    if entry:
        ptype = entry['type']
        display = entry['display']
        group = entry['group']
        order = entry.get('order', 99)
    else:
        ptype = 'str'
        display = key
        group = 'extended'
        order = 99

    # Cast value based on type
    value = raw_value
    try:
        if ptype == 'int':
            value = int(float(raw_value))  # handles "20.0" -> 20
        elif ptype == 'float':
            value = float(raw_value)
    except (ValueError, TypeError):
        pass  # keep as string if cast fails

    return {
        'key': key,
        'display': display,
        'value': value,
        'type': ptype,
        'group': group,
        'order': order,
    }


def parse_params_line(params_line):
    """
    Parse a params line like "Steps: 20, Sampler: Euler a Karras, CFG scale: 4.0, ..."
    into a list of cast param dicts.

    Handles the tricky splitting where values can contain commas only if the next
    token starts with a known key pattern (capitalized word followed by colon).
    """
    if not params_line or not isinstance(params_line, str):
        return []

    # Strip CivitAI resources first (contains commas that would confuse splitting)
    civitai_match = re.search(r',?\s*Civitai resources: \[.*\]', params_line)
    if civitai_match:
        params_line = params_line[:civitai_match.start()]

    # Split on ", Key: " boundaries using lookahead for "Key:" pattern
    # A key is: word characters (including spaces) followed by a colon and space
    # We split on ", " only when followed by a key pattern
    tokens = re.split(r',\s+(?=[A-Z][A-Za-z0-9 _]*:\s)', params_line)

    results = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # Split on first ": " to get key and value
        colon_pos = token.find(': ')
        if colon_pos < 0:
            continue

        key = token[:colon_pos].strip()
        value = token[colon_pos + 2:].strip()

        if key and value:
            results.append(cast_param(key, value))

    # Sort by order (core params in defined order, extended params at end)
    results.sort(key=lambda p: p['order'])
    return results
