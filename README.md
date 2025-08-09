# image-db-to-zarr
- Extract and process image data from ImageXpress Pico, Molecular Devices, CellReporterXpress experiment and image db files
- Export to ome-zarr supporting Screen Plate Well / High Content Screening format




### Example output of converter.convert()
```

> source = ImageDbSource(input_filename)

> print_dict(source.init_metadata())

dim_order: tczyx
time_points: 0
levels: 0 1 2 3 4 5 6 7 8 9 10
image_files:
        0: D:/slides/DB/TestData1\images-0.db
DateCreated: 2023-06-01 13:50:24.080571
Creator: Me
Name: TestRon
acquisitions:
-   Name: TestData
        Description: Preset Protocol for the OrganoPlate 3-lane (Mimetas B.V.)
        DateCreated: 2023-06-01 13:50:28.034732
        DateModified: 2023-06-01 13:50:30.669354
channels:
-   ChannelNumber: 0
        Emission: 470
        Excitation: 387
        Dye: DAPI
        Color: 1CA9C9
-   ChannelNumber: 1
        Emission: 0
        Excitation: 0
        Dye: None
        Color: FFFFFF
num_channels: 2
wells:
        B2:
                Name: B2
                ZoneIndex: 25
                CoordX: 1
                CoordY: 1
        B5:
                Name: B5
                ZoneIndex: 28
                CoordX: 4
                CoordY: 1
        E2:
                Name: E2
                ZoneIndex: 97
                CoordX: 1
                CoordY: 4
        E5:
                Name: E5
                ZoneIndex: 100
                CoordX: 4
                CoordY: 4
well_info:
        SensorSizeYPixels: 2008
        SensorSizeXPixels: 2008
        Objective: 10.0
        PixelSizeUm: 0.69
        SensorBitness: 12
        SitesX: 2
        SitesY: 1
        rows: A B C D E F G H I J K L M N O P
        columns: 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
        num_sites: 2
        fields: 0 1
        max_sizex_um: 2771.04
        max_sizey_um: 1385.52
bits_per_pixel: 12
dtype: uint16
max_data_size: 129026048

> source.print_well_matrix()

 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
A
B    +        +
C
D
E    +        +
F
G
H
I
J
K
L
M
N
O
P

> source.print_timepoint_well_matrix()

Timepoint B02 B05 E02 E05
        0  +   +   +   +

> print_hbytes(source.get_total_data_size())

Total data size:    123.0MB

> writer = OmeZarrWriter(zarr_version=zarr_version, ome_version=ome_version, verbose=verbose)
> writer.write(output_path, source, name=name)

Total data written: 123.0MB

Time convert TestData1 to zarr: 6.4 (13.2) seconds
```