from datetime import datetime, timedelta
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


def add_leading_zero(input_string, num_digits=2):
    output = str(input_string)
    while len(output) < num_digits:
        output = '0' + output
    return output


def remove_leading_zeros(well_name):
    row, col = split_well_name(well_name, remove_leading_zeros=True)
    return f'{row}{col}'


def convert_dotnet_ticks_to_datetime(net_ticks):
    return datetime(1, 1, 1) + timedelta(microseconds=net_ticks // 10)


def convert_to_um(value, unit):
    conversions = {
        'nm': 1e-3,
        'µm': 1, 'um': 1, 'micrometer': 1,
        'mm': 1e3, 'millimeter': 1e3,
        'cm': 1e4, 'centimeter': 1e4,
        'm': 1e6, 'meter': 1e6
    }
    return value * conversions.get(unit, 1)
