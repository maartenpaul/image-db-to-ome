import sqlite3


class DBReader:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.conn.row_factory = DBReader.dict_factory

    @staticmethod
    def dict_factory(cursor, row):
        dct = {}
        for index, column in enumerate(cursor.description):
            dct[column[0]] = row[index]
        return dct

    def fetch_all(self, query, params=(), return_dicts=True):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        dct = cursor.fetchall()
        if return_dicts:
            values = dct
        else:
            values = [list(row.values())[0] for row in dct]
        return values

    def close(self):
        self.conn.close()
