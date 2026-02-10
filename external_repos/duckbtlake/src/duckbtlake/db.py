import duckdb

con = duckdb.connect()
con.install_extension("ducklake")

con.load_extension("ducklake")

con.execute("ATTACH 'ducklake:metadata.ducklake' AS lake")
con.execute("USE lake")
