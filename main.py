#!/usr/bin/env python3
import argparse
import asyncio
import time
import os
import shutil
import subprocess
import edge_tts as tts
import re
import requests
import uuid
import logging

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s|%(levelname).1s| %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("t2s")

VOICE = "en-US-EmmaMultilingualNeural"
OUTPUT_FILE = "output/audio.mp3"
SRT_FILE = "output/audio.srt"


def clean(s):
    s = s.replace("\\n", "")
    s = re.sub(r"[^\w\s.,!?]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


SENTENCES_PER_CHUNK = 1


def split(text: str, chunk_size=SENTENCES_PER_CHUNK, min_sent=10) -> list:
    # Pre-compile regex for better performance
    sentence_pattern = re.compile(r"(?<!\w\.\w.)(?<=\.|\?|\!)\s")
    sentences = sentence_pattern.split(text.strip())

    chunks = []
    temp = []

    for sentence in sentences:
        sentence = sentence.strip()

        # More efficient merge condition
        if temp and len(sentence.split()) < min_sent:
            # Directly concatenate instead of replacing the last element
            temp[-1] = f"{temp[-1]} {sentence}"
        else:
            temp.append(sentence)

        # Move chunks when reaching chunk_size
        if len(temp) >= chunk_size:
            chunks.append(" ".join(temp))
            # Reset temp with empty list (more efficient than reassignment)
            temp.clear()

    # Don't forget remaining sentences
    if temp:
        chunks.append(" ".join(temp))

    return chunks


async def process_text(text):
    sentences = re.split(r"(?<=[.!?]) +", text)
    chunks = []

    for i in range(0, len(sentences), SENTENCES_PER_CHUNK):
        chunk = " ".join(sentences[i : i + SENTENCES_PER_CHUNK])
        chunks.append(chunk)
    return chunks


OUTPUT_FOLDER = "output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


async def createAudio(chunk, index, dir, args, sem: asyncio.Semaphore):
    async with sem:
        comm = tts.Communicate(
            chunk,
            voice=args.voice,
            rate=args.rate,
            volume=args.volume,
            pitch=args.pitch,
        )
        path = os.path.join(dir, f"audio_{index}.mp3")

        with open(path, "wb") as audio_file:
            async for part in comm.stream():
                if part["type"] == "audio":
                    audio_file.write(part["data"])

        return path


async def amain(args) -> None:
    start = time.time()
    text = ""
    with open("input.txt", "r", encoding="utf-8") as file:
        text = file.read()

    # Clean the input text and show character count
    text = clean(text)
    logger.info(f"Character count: {len(text)}")

    # Split text into manageable chunks for processing
    chunks = split(text, SENTENCES_PER_CHUNK)
    logger.info(f"Text split into {len(chunks)} chunks")

    # Create a temporary directory with unique ID to store audio chunks
    tmp_dir = f"tmp/{uuid.uuid4()}"
    os.makedirs(tmp_dir, exist_ok=True)

    # Limit concurrent API calls with semaphore to prevent rate limiting
    semaphore = asyncio.Semaphore(15)

    # Create audio files for each text chunk in parallel
    logger.info(f"Starting audio generation with {semaphore._value} concurrent tasks")
    tasks = [createAudio(c, i, tmp_dir, args, semaphore) for i, c in enumerate(chunks)]
    await asyncio.gather(*tasks)

    # Combine all audio files into single output file
    logger.info("Combining audio chunks...")
    subprocess.run(f"cat {tmp_dir}/audio_*.mp3 > {OUTPUT_FILE}", shell=True)

    # Calculate and display processing time
    spend = time.time() - start
    logger.info(f"Audio created in {spend:.2f}s > {OUTPUT_FILE}")

    uploadAudio(args.name)

    shutil.rmtree(tmp_dir)

    logger.info(f"Audio URL: https://cdn.laobo.xyz/audios/{args.name}")


def uploadAudio(name: str) -> None:
    start = time.time()
    logger.info(f"Uploading {OUTPUT_FILE}...")
    r = requests.get("https://laobo.xyz/api/preup", params={"name": name}, timeout=5)
    r.raise_for_status()
    d = r.json()
    url = d["url"]

    r = requests.put(url, data=open(OUTPUT_FILE, "rb"), timeout=60)
    r.raise_for_status()

    spend = time.time() - start
    logger.info(f"Uploaded: {spend:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TTS CLI")
    parser.add_argument("name", help="Your name")
    parser.add_argument(
        "-v",
        "--voice",
        type=str,
        default=VOICE,
    )
    parser.add_argument(
        "-r",
        "--rate",
        type=str,
        default="+0%",
    )
    parser.add_argument(
        "-vol",
        "--volume",
        type=str,
        default="+0%",
    )
    parser.add_argument(
        "-p",
        "--pitch",
        type=str,
        default="+0Hz",
    )
    args = parser.parse_args()

    asyncio.run(amain(args))
