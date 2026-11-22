import csv
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from tqdm import tqdm
import yt_dlp
TRACKS_FILE =Path ("tracks.csv")
DOWNLOAD_DIR =Path ("downloads_mp3")
FAILED_LOG =Path ("failed_downloads.txt")
def safe_filename (value :str )->str :
    cleaned =re .sub (r"[\\/:*?\"<>|]+","_",value ).strip ()
    return cleaned [:180 ]if cleaned else "track"
def check_ffmpeg ()->None :
    try :
        subprocess .run (
        ["ffmpeg","-version"],
        check =True ,
        stdout =subprocess .DEVNULL ,
        stderr =subprocess .DEVNULL ,
        )
    except Exception as exc :
        raise RuntimeError (
        "FFmpeg не найден. Установите FFmpeg и добавьте в PATH."
        )from exc
def read_tracks ()->list [dict [str ,str ]]:
    if not TRACKS_FILE .exists ():
        raise FileNotFoundError (
        f"Не найден {TRACKS_FILE }. Сначала запустите: python build_table.py"
        )
    with TRACKS_FILE .open ("r",encoding ="utf-8-sig",newline ="")as f :
        reader =csv .DictReader (f )
        tracks =[row for row in reader ]
    if not tracks :
        raise RuntimeError ("Файл tracks.csv пуст.")
    return tracks
def make_ydl_options (output_template :str )->dict [str ,Any ]:
    return {
    "format":"bestaudio/best",
    "outtmpl":output_template ,
    "noplaylist":True ,
    "quiet":True ,
    "no_warnings":True ,
    "default_search":"ytsearch1",
    "postprocessors":[
    {
    "key":"FFmpegExtractAudio",
    "preferredcodec":"mp3",
    "preferredquality":"192",
    }
    ],
    }
def download_all (tracks :list [dict [str ,str ]])->None :
    DOWNLOAD_DIR .mkdir (parents =True ,exist_ok =True )
    failed :list [str ]=[]
    progress =tqdm (tracks ,desc ="Скачивание треков",unit ="трек")
    for row in progress :
        title =(row .get ("title")or "").strip ()
        artist =(row .get ("artist")or "").strip ()
        query =(row .get ("query")or "").strip ()or f"{title } {artist }".strip ()
        filename =safe_filename (f"{title } - {artist }"if artist else title )
        outtmpl =str (DOWNLOAD_DIR /f"{filename }.%(ext)s")
        progress .set_postfix_str (filename [:45 ],refresh =False )
        try :
            with yt_dlp .YoutubeDL (make_ydl_options (outtmpl ))as ydl :
                ydl .download ([query ])
        except Exception as exc :
            failed .append (f"{query } :: {exc }")
    if failed :
        FAILED_LOG .write_text ("\n".join (failed ),encoding ="utf-8")
        print (f"\nЧасть треков не скачалась. Подробности: {FAILED_LOG .resolve ()}")
    else :
        if FAILED_LOG .exists ():
            FAILED_LOG .unlink ()
        print ("\nВсе треки успешно скачаны.")
    print (f"Папка с mp3: {DOWNLOAD_DIR .resolve ()}")
def main ()->None :
    check_ffmpeg ()
    tracks =read_tracks ()
    download_all (tracks )
if __name__ =="__main__":
    try :
        main ()
    except Exception as error :
        print (f"Ошибка: {error }")
        sys .exit (1 )