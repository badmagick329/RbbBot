from TikTokApi import TikTokApi
from argparse import ArgumentParser


def main():
    parser = ArgumentParser()
    parser.add_argument("video_id", type=int)
    parser.add_argument("-o", type=str)
    args = parser.parse_args()
    if args.video_id:
        video_id = args.video_id
        filename = args.o if args.o else f"{video_id}.mp4"
        download(args.video_id, filename)
    else:
        print("Please provide a video id")


def download(video_id: int, filename: str) -> None:
    with TikTokApi() as api:
        video = api.video(id=video_id)
        video_data = video.bytes()
        # video_desc, video_id = video.as_dict["desc"], video.as_dict["id"]
        video_id = video.as_dict["id"]
        with open(filename, "wb") as f:
            f.write(video_data)

        return filename


if __name__ == "__main__":
    main()
