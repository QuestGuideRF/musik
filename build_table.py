import csv
import re
from pathlib import Path
SOURCE_FILE =Path ("1.txt")
OUTPUT_FILE =Path ("tracks.csv")
def is_duration (value :str )->bool :
    return bool (re .fullmatch (r"\d{1,2}:\d{2}",value .strip ()))
def normalize_lines (text :str )->list [str ]:
    lines =[line .strip ()for line in text .splitlines ()]
    return [line for line in lines if line ]
def clean_meta_tokens (tokens :list [str ])->list [str ]:
    cleaned :list [str ]=[]
    for token in tokens :
        value =token .strip ()
        if not value :
            continue
        if value in {"и",",",",,",", ,"}:
            continue
        cleaned .append (value )
    return cleaned
def parse_tracks (lines :list [str ])->list [dict [str ,str ]]:
    tracks :list [dict [str ,str ]]=[]
    i =0
    while i <len (lines ):
        title =lines [i ]
        i +=1
        meta_tokens :list [str ]=[]
        duration =""
        while i <len (lines ):
            current =lines [i ]
            if is_duration (current ):
                duration =current
                i +=1
                break
            meta_tokens .append (current )
            i +=1
        meta =clean_meta_tokens (meta_tokens )
        artist =meta [0 ]if meta else ""
        extra =" | ".join (meta [1 :])if len (meta )>1 else ""
        tracks .append (
        {
        "title":title ,
        "artist":artist ,
        "extra_info":extra ,
        "duration":duration .strip (),
        "query":f"{title } {artist }".strip (),
        }
        )
    return tracks
def main ()->None :
    if not SOURCE_FILE .exists ():
        raise FileNotFoundError (f"Не найден файл: {SOURCE_FILE .resolve ()}")
    text =SOURCE_FILE .read_text (encoding ="utf-8",errors ="ignore")
    lines =normalize_lines (text )
    tracks =parse_tracks (lines )
    with OUTPUT_FILE .open ("w",newline ="",encoding ="utf-8-sig")as csvfile :
        writer =csv .DictWriter (
        csvfile ,
        fieldnames =["id","title","artist","extra_info","duration","query"],
        )
        writer .writeheader ()
        for idx ,track in enumerate (tracks ,start =1 ):
            writer .writerow ({"id":idx ,**track })
    print (f"Готово: {OUTPUT_FILE .resolve ()} (треков: {len (tracks )})")
if __name__ =="__main__":
    main ()