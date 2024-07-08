import os
import tweepy
import schedule
import time
from PIL import Image
import io
import boto3
from botocore.exceptions import ClientError
from stability_sdk import client
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
from dotenv import load_dotenv

load_dotenv()

# X API設定
auth = tweepy.OAuthHandler(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"))
auth.set_access_token(os.getenv("TWITTER_ACCESS_TOKEN"), os.getenv("TWITTER_ACCESS_TOKEN_SECRET"))
api = tweepy.API(auth)

# AWS S3設定
s3 = boto3.client('s3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# Stable Diffusion API設定
stability_api = client.StabilityInference(
    key=os.getenv("STABILITY_KEY"),
    verbose=True,
)

def get_buzz_words():
    trends = api.get_place_trends(1)  # 1はワールドワイドのトレンド
    return [trend['name'] for trend in trends[0]['trends'][:5]]  # 上位5つのトレンドを取得

def generate_image(prompt):
    answers = stability_api.generate(
        prompt=prompt,
        seed=992446758,
        steps=30,
        cfg_scale=8.0,
        width=512,
        height=512,
        samples=1,
        sampler=generation.SAMPLER_K_DPMPP_2M
    )
    for resp in answers:
        for artifact in resp.artifacts:
            if artifact.type == generation.ARTIFACT_IMAGE:
                img = Image.open(io.BytesIO(artifact.binary))
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                return img_byte_arr
    return None

def upload_to_s3(image_bytes, bucket, key):
    try:
        s3.put_object(Bucket=bucket, Key=key, Body=image_bytes)
    except ClientError as e:
        print(f"An error occurred: {e}")
        return None
    return f"https://{bucket}.s3.amazonaws.com/{key}"

def post_to_twitter(image_url, message):
    try:
        api.update_status_with_media(status=message, filename="image.png", file=image_url)
    except tweepy.TweepError as e:
        print(f"An error occurred: {e}")

def main_job():
    buzz_words = get_buzz_words()
    prompt = " ".join(buzz_words)
    image_bytes = generate_image(prompt)
    if image_bytes:
        image_url = upload_to_s3(image_bytes, os.getenv("AWS_S3_BUCKET"), f"image_{int(time.time())}.png")
        if image_url:
            message = f"Generated image based on trends: {', '.join(buzz_words)}"
            post_to_twitter(image_url, message)

schedule.every(1).hours.do(main_job)

if __name__ == "__main__":
    while True:
        schedule.run_pending()
        time.sleep(1)