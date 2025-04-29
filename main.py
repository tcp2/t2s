#!/usr/bin/env python3
import os
import re
import time
import uuid
import shutil
import argparse
import asyncio
import subprocess
import logging
import requests
from dataclasses import dataclass
from typing import List
from edge_tts import Communicate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s|%(levelname).1s| %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TTS")


@dataclass
class Config:
    name: str
    voice: str = "en-US-EmmaMultilingualNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    hook: str = ""


class TextToSpeech:
    OUTPUT_DIR: str = "output"
    TMP_DIR: str = "tmp"
    OUTPUT_FILE: str = os.path.join(OUTPUT_DIR, "audio.mp3")

    def __init__(self) -> None:
        self.config = parse_args()
        self.semaphore = asyncio.Semaphore(15)
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

    def split_text(
        self, text: str, chunk_size: int = 1, min_words: int = 10
    ) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s", text.strip())
        chunks: List[str] = []
        temp: List[str] = []
        for s in sentences:
            s = s.strip()
            if temp and len(s.split()) < min_words:
                temp[-1] += f" {s}"
            else:
                temp.append(s)
            if len(temp) >= chunk_size:
                chunks.append(" ".join(temp))
                temp.clear()
        if temp:
            chunks.append(" ".join(temp))
        return chunks

    async def generate_audio(self, text: str, index: int, out_dir: str) -> str:
        async with self.semaphore:
            comm = Communicate(
                text,
                voice=self.config.voice,
                rate=self.config.rate,
                volume=self.config.volume,
                pitch=self.config.pitch,
            )
            file_path: str = os.path.join(out_dir, f"audio_{index}.mp3")
            with open(file_path, "wb") as f:
                async for part in comm.stream():
                    if part["type"] == "audio":
                        f.write(part["data"])
            return file_path

    def combine_audio(self, dir_path: str) -> None:
        subprocess.run(f"cat {dir_path}/audio_*.mp3 > {self.OUTPUT_FILE}", shell=True)

    def upload(self) -> None:
        logger.info(f"Uploading {self.OUTPUT_FILE}...")
        r = requests.post(
            "https://laobo.xyz/api/preup", data={"name": self.config.name}, timeout=5
        )
        r.raise_for_status()
        url = r.json()["url"]
        with open(self.OUTPUT_FILE, "rb") as f:
            requests.put(url, data=f, timeout=60).raise_for_status()
        logger.info("Uploaded successfully.")

    async def run(self) -> None:
        start: float = time.time()
        with open("input.txt", "r", encoding="utf-8") as f:
            raw_text: str = f.read()
        cleaned: str = clean_text(raw_text)

        logger.info(f"Character count: {len(cleaned)}")
        chunks: List[str] = self.split_text(cleaned)

        logger.info(f"Text split into {len(chunks)} chunks")
        tmp_dir: str = os.path.join(self.TMP_DIR, str(uuid.uuid4()))
        os.makedirs(tmp_dir, exist_ok=True)

        logger.info(f"Generating audio with {self.semaphore._value} workers...")
        tasks = [self.generate_audio(c, i, tmp_dir) for i, c in enumerate(chunks)]
        await asyncio.gather(*tasks)

        logger.info("Combining audio...")
        self.combine_audio(tmp_dir)

        logger.info(f"Audio created in {time.time() - start:.2f}s → {self.OUTPUT_FILE}")
        self.upload()
        shutil.rmtree(tmp_dir)

        logger.info(f"Audio URL: https://cdn.laobo.xyz/audios/{self.config.name}")

        if self.config.hook:
            requests.get(self.config.hook, timeout=5)
            logger.info(f"Webhook sent to {self.config.hook}")


def parse_args() -> Config:
    p = argparse.ArgumentParser(description="TTS CLI")
    p.add_argument("name", help="Output filename")
    p.add_argument("-v", "--voice", default="en-US-EmmaMultilingualNeural")
    p.add_argument("-r", "--rate", default="+0%")
    p.add_argument("-vol", "--volume", default="+0%")
    p.add_argument("-p", "--pitch", default="+0Hz")
    p.add_argument("-ho", "--hook", default="")
    return Config(**vars(p.parse_args()))


def clean_text(text: str) -> str:
    return re.sub(
        r"\s+", " ", re.sub(r"[^\w\s.,!?]", "", text.replace("\\n", ""))
    ).strip()


if __name__ == "__main__":
    tts = TextToSpeech()
    asyncio.run(tts.run())
