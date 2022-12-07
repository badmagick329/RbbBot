from argparse import ArgumentParser

from TikTokApi import TikTokApi


def main():
    parser = ArgumentParser()
    parser.add_argument("video_id", type=int)
    parser.add_argument("-o", type=str)
    args = parser.parse_args()
    if args.video_id:
        video_id = args.video_id
        filename = args.o if args.o else f"{video_id}.mp4"
        result = download(args.video_id, filename)
        if not result:
            exit(1)
        print(f"Downloaded video to {result}")
        exit(0)
    else:
        print("Please provide a video id")


def download(video_id: int, filename: str) -> str | None:
    retries = 5
    with TikTokApi() as api:
        video = api.video(id=video_id)
        video_data = video.bytes()
        print(f"Video size is {len(video_data)} bytes")
        while len(video_data) < 1000:
            print("Video data is too small, retrying")
            if retries > 0:
                retries -= 1
                video = api.video(id=video_id)
                video_data = video.bytes()
            else:
                print("Failed to download video")
                return
        # video_desc, video_id = video.as_dict["desc"], video.as_dict["id"]
        video_id = video.as_dict["id"]
        with open(filename, "wb") as f:
            f.write(video_data)

        return filename


if __name__ == "__main__":
    main()
