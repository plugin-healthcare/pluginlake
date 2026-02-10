import marimo

__generated_with = "0.14.10"
app = marimo.App()


@app.cell
def _():
    from pathlib import Path

    import cbsodata
    import polars as pl

    cbs = Path(__file__).parent.parent / "datalake/cbs"
    return cbs, cbsodata, pl


@app.cell
def _(cbs):
    list(cbs.glob("*.parquet"))
    return


@app.cell
def _(cbs, pl):
    df = pl.read_parquet(cbs / "cbs-83982NED.parquet")
    df
    return (df,)


@app.cell
def _(df):
    df.select("RegioS").unique()
    return


@app.cell
def _(cbsodata):
    cbsodata.get_info("83982NED")
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
