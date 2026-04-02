def loadCSV(csv_file_name):
    rows = []
    csv_file = open(csv_file_name, 'r')
    csv_fields = [f.lower() for f in csv_file.readline().strip().split(',')]

    for line in csv_file:
        line_dict = dict((f, v) for f, v in zip(csv_fields, line.strip().split(',')))
        rows.append(line_dict)

    csv_file.close()
    return csv_fields, rows
