import argparse
from datetime import datetime

import fs_utils as fu


def test_webdav(webdav_url: str):

    try:
        fs = fu.get_wd_fs(webdav_url)
    except:
        print("Could not create WebdavFileSystem object")
        return
    # test listing files
    try:
        print(fu.listdir(path="/data", fs=fs, detail=False))
    except Exception as e:
        print(e)

    # test reading file
    try:
        print(fu.read_file(path="data/testfile.txt", fs=fs))
    except Exception as e:
        print(e)

    # test writing file
    try:
        print(
            "succesfull!"
            if fu.write_file(
                path="/data/testfile.txt",
                content=f"Hello World! the time is {datetime.now().strftime('%H:%M:%S')}",
                fs=fs,
            )
            else "unsuccesfull!"
        )
    except Exception as e:
        print(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test webdav client")
    parser.add_argument("--webdav_url", type=str, help="Webdav url", required=True)
    args = parser.parse_args()
    test_webdav(args.webdav_url)
