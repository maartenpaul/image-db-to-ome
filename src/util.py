import re


def split_well_name(well_name, remove_leading_zeros=True, col_as_int=False):
    matches = re.findall(r'(\D+)(\d+)', well_name)
    if len(matches) > 0:
        row, col = matches[0]
        if col_as_int or remove_leading_zeros:
            try:
                col = int(col)
            except ValueError:
                pass
        if not col_as_int:
            col = str(col)
        return row, col
    else:
        raise ValueError(f"Invalid well name format: {well_name}. Expected format like 'A1', 'B2', etc.")
