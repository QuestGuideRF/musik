import csv
import queue
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog ,messagebox ,ttk
import yt_dlp
APP_TITLE ="Создатель музыки и загрузчик"
DEFAULT_TEXT_FILE =Path ("1.txt")
DEFAULT_CSV_FILE =Path ("tracks.csv")
DEFAULT_DOWNLOAD_DIR =Path ("downloads_mp3")
FAILED_LOG =Path ("failed_downloads.txt")
@dataclass
class Track :
    track_id :int
    title :str
    artist :str
    extra_info :str
    duration :str
    query :str
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
        if value in {"Рё",",",",,",", ,"}:
            continue
        cleaned .append (value )
    return cleaned
def parse_tracks (text :str )->list [Track ]:
    lines =normalize_lines (text )
    tracks :list [Track ]=[]
    index =0
    track_id =1
    while index <len (lines ):
        title =lines [index ]
        index +=1
        meta_tokens :list [str ]=[]
        duration =""
        while index <len (lines ):
            current =lines [index ]
            if is_duration (current ):
                duration =current
                index +=1
                break
            meta_tokens .append (current )
            index +=1
        meta =clean_meta_tokens (meta_tokens )
        artist =meta [0 ]if meta else ""
        extra_info =" | ".join (meta [1 :])if len (meta )>1 else ""
        query =f"{title } {artist }".strip ()
        tracks .append (
        Track (
        track_id =track_id ,
        title =title ,
        artist =artist ,
        extra_info =extra_info ,
        duration =duration ,
        query =query ,
        )
        )
        track_id +=1
    return tracks
def export_tracks_to_csv (tracks :list [Track ],destination :Path )->None :
    with destination .open ("w",newline ="",encoding ="utf-8-sig")as csvfile :
        writer =csv .DictWriter (
        csvfile ,
        fieldnames =["id","title","artist","extra_info","duration","query"],
        )
        writer .writeheader ()
        for track in tracks :
            writer .writerow (
            {
            "id":track .track_id ,
            "title":track .title ,
            "artist":track .artist ,
            "extra_info":track .extra_info ,
            "duration":track .duration ,
            "query":track .query ,
            }
            )
def safe_filename (value :str )->str :
    cleaned =re .sub (r'[\\/:*?"<>|]+',"_",value ).strip ()
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
        raise RuntimeError ("FFmpeg не найден. Установите FFmpeg и добавьте его в PATH.")from exc
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
class MusicApp :
    def __init__ (self ,root :tk .Tk )->None :
        self .root =root
        self .root .title (APP_TITLE )
        self .root .geometry ("1380x860")
        self .root .minsize (1120 ,720 )
        self .root .configure (bg ="#0f172a")
        self .tracks :list [Track ]=[]
        self .track_map :dict [str ,Track ]={}
        self .queue_items :list [str ]=[]
        self .download_queue :queue .Queue [Track |None ]=queue .Queue ()
        self .worker_events :queue .Queue [tuple [str ,str ,str ]]=queue .Queue ()
        self .failed_downloads :list [str ]=[]
        self .is_downloading =False
        self .download_dir_var =tk .StringVar (value =str (DEFAULT_DOWNLOAD_DIR .resolve ()))
        self .status_var =tk .StringVar (value ="Готово к работе")
        self .summary_var =tk .StringVar (value ="Треков: 0 | В очереди: 0")
        self ._build_style ()
        self ._build_layout ()
        self ._load_default_text ()
        self .root .after (150 ,self ._process_worker_events )
    def _build_style (self )->None :
        style =ttk .Style ()
        style .theme_use ("clam")
        style .configure (".",font =("Следуйте пользовательскому интерфейсу",10 ))
        style .configure ("Card.TFrame",background ="#111827")
        style .configure ("Shell.TFrame",background ="#0f172a")
        style .configure (
        "Hero.TLabel",
        background ="#111827",
        foreground ="#f8fafc",
        font =("Segoe UI Полужирный шрифт",20 ),
        )
        style .configure (
        "Muted.TLabel",
        background ="#111827",
        foreground ="#94a3b8",
        font =("Следуйте пользовательскому интерфейсу",10 ),
        )
        style .configure (
        "Section.TLabel",
        background ="#111827",
        foreground ="#e2e8f0",
        font =("Segoe UI Полужирный шрифт",11 ),
        )
        style .configure (
        "Primary.TButton",
        padding =(16 ,10 ),
        background ="#f59e0b",
        foreground ="#111827",
        borderwidth =0 ,
        focusthickness =0 ,
        )
        style .map (
        "Primary.TButton",
        background =[("active","#fbbf24"),("disabled","#6b7280")],
        foreground =[("disabled","#e5e7eb")],
        )
        style .configure (
        "Secondary.TButton",
        padding =(14 ,9 ),
        background ="#1f2937",
        foreground ="#f8fafc",
        borderwidth =0 ,
        )
        style .map ("Secondary.TButton",background =[("active","#334155")])
        style .configure (
        "Custom.Treeview",
        background ="#0b1220",
        fieldbackground ="#0b1220",
        foreground ="#e5e7eb",
        rowheight =30 ,
        borderwidth =0 ,
        )
        style .configure (
        "Custom.Treeview.Heading",
        background ="#172033",
        foreground ="#f8fafc",
        font =("Segoe UI Полужирный шрифт",10 ),
        relief ="flat",
        )
        style .map (
        "Custom.Treeview",
        background =[("selected","#1d4ed8")],
        foreground =[("selected","#ffffff")],
        )
        style .configure (
        "Custom.Vertical.TScrollbar",
        background ="#1f2937",
        troughcolor ="#0b1220",
        arrowcolor ="#e5e7eb",
        bordercolor ="#0b1220",
        )
    def _build_layout (self )->None :
        shell =ttk .Frame (self .root ,style ="Shell.TFrame",padding =18 )
        shell .pack (fill ="both",expand =True )
        shell .columnconfigure (0 ,weight =2 )
        shell .columnconfigure (1 ,weight =1 )
        shell .rowconfigure (1 ,weight =1 )
        hero =ttk .Frame (shell ,style ="Card.TFrame",padding =18 )
        hero .grid (row =0 ,column =0 ,columnspan =2 ,sticky ="nsew",pady =(0 ,14 ))
        hero .columnconfigure (0 ,weight =1 )
        ttk .Label (hero ,text =APP_TITLE ,style ="Hero.TLabel").grid (row =0 ,column =0 ,sticky ="w")
        ttk .Label (
        hero ,
        text ="Из текста в таблицу и сразу в очередь загрузки mp3.",
        style ="Muted.TLabel",
        ).grid (row =1 ,column =0 ,sticky ="w",pady =(6 ,0 ))
        ttk .Label (hero ,textvariable =self .summary_var ,style ="Muted.TLabel").grid (
        row =0 ,column =1 ,rowspan =2 ,sticky ="e"
        )
        left =ttk .Frame (shell ,style ="Card.TFrame",padding =16 )
        left .grid (row =1 ,column =0 ,sticky ="nsew",padx =(0 ,10 ))
        left .columnconfigure (0 ,weight =1 )
        left .rowconfigure (2 ,weight =1 )
        left .rowconfigure (4 ,weight =2 )
        ttk .Label (left ,text ="Исходный текст",style ="Section.TLabel").grid (row =0 ,column =0 ,sticky ="w")
        toolbar =ttk .Frame (left ,style ="Card.TFrame")
        toolbar .grid (row =1 ,column =0 ,sticky ="ew",pady =(10 ,10 ))
        for idx in range (5 ):
            toolbar .columnconfigure (idx ,weight =1 if idx ==4 else 0 )
        ttk .Button (toolbar ,text ="Открыть TXT",style ="Secondary.TButton",command =self .load_text_file ).grid (
        row =0 ,column =0 ,padx =(0 ,8 )
        )
        ttk .Button (toolbar ,text ="Собрать таблицу",style ="Primary.TButton",command =self .build_table ).grid (
        row =0 ,column =1 ,padx =(0 ,8 )
        )
        ttk .Button (toolbar ,text ="Экспорт CSV",style ="Secondary.TButton",command =self .export_csv ).grid (
        row =0 ,column =2 ,padx =(0 ,8 )
        )
        ttk .Button (
        toolbar ,text ="В очередь все",style ="Secondary.TButton",command =self .queue_all_tracks
        ).grid (row =0 ,column =3 ,padx =(0 ,8 ))
        text_frame =tk .Frame (left ,bg ="#0b1220",highlightthickness =1 ,highlightbackground ="#1f2937")
        text_frame .grid (row =2 ,column =0 ,sticky ="nsew")
        text_frame .columnconfigure (0 ,weight =1 )
        text_frame .rowconfigure (0 ,weight =1 )
        self .text_input =tk .Text (
        text_frame ,
        wrap ="word",
        bg ="#0b1220",
        fg ="#e5e7eb",
        insertbackground ="#f8fafc",
        selectbackground ="#1d4ed8",
        relief ="flat",
        font =("Consolas",11 ),
        padx =14 ,
        pady =14 ,
        )
        self .text_input .grid (row =0 ,column =0 ,sticky ="nsew")
        text_scroll =ttk .Scrollbar (
        text_frame ,orient ="vertical",command =self .text_input .yview ,style ="Custom.Vertical.TScrollbar"
        )
        text_scroll .grid (row =0 ,column =1 ,sticky ="ns")
        self .text_input .configure (yscrollcommand =text_scroll .set )
        ttk .Label (left ,text ="Таблица треков",style ="Section.TLabel").grid (
        row =3 ,column =0 ,sticky ="w",pady =(14 ,8 )
        )
        table_wrap =ttk .Frame (left ,style ="Card.TFrame")
        table_wrap .grid (row =4 ,column =0 ,sticky ="nsew")
        table_wrap .columnconfigure (0 ,weight =1 )
        table_wrap .rowconfigure (0 ,weight =1 )
        columns =("id","title","artist","extra_info","duration","query")
        self .tracks_tree =ttk .Treeview (
        table_wrap ,
        columns =columns ,
        show ="headings",
        style ="Custom.Treeview",
        selectmode ="extended",
        )
        self .tracks_tree .grid (row =0 ,column =0 ,sticky ="nsew")
        for column ,width in {
        "id":60 ,
        "title":260 ,
        "artist":180 ,
        "extra_info":240 ,
        "duration":90 ,
        "query":300 ,
        }.items ():
            self .tracks_tree .heading (column ,text =column .upper ())
            self .tracks_tree .column (column ,width =width ,anchor ="w")
        tracks_scroll =ttk .Scrollbar (
        table_wrap ,orient ="vertical",command =self .tracks_tree .yview ,style ="Custom.Vertical.TScrollbar"
        )
        tracks_scroll .grid (row =0 ,column =1 ,sticky ="ns")
        self .tracks_tree .configure (yscrollcommand =tracks_scroll .set )
        track_actions =ttk .Frame (left ,style ="Card.TFrame")
        track_actions .grid (row =5 ,column =0 ,sticky ="ew",pady =(10 ,0 ))
        ttk .Button (
        track_actions ,
        text ="В очередь выбранные",
        style ="Secondary.TButton",
        command =self .queue_selected_tracks ,
        ).pack (side ="left")
        right =ttk .Frame (shell ,style ="Card.TFrame",padding =16 )
        right .grid (row =1 ,column =1 ,sticky ="nsew")
        right .columnconfigure (0 ,weight =1 )
        right .rowconfigure (4 ,weight =1 )
        right .rowconfigure (7 ,weight =1 )
        ttk .Label (right ,text ="Скачивание",style ="Section.TLabel").grid (row =0 ,column =0 ,sticky ="w")
        ttk .Label (
        right ,
        text ="Папка для mp3",
        style ="Muted.TLabel",
        ).grid (row =1 ,column =0 ,sticky ="w",pady =(10 ,4 ))
        folder_row =ttk .Frame (right ,style ="Card.TFrame")
        folder_row .grid (row =2 ,column =0 ,sticky ="ew")
        folder_row .columnconfigure (0 ,weight =1 )
        folder_entry =tk .Entry (
        folder_row ,
        textvariable =self .download_dir_var ,
        bg ="#0b1220",
        fg ="#e5e7eb",
        insertbackground ="#f8fafc",
        relief ="flat",
        font =("Следуйте пользовательскому интерфейсу",10 ),
        )
        folder_entry .grid (row =0 ,column =0 ,sticky ="ew",ipady =8 ,padx =(0 ,8 ))
        ttk .Button (folder_row ,text ="Выбрать",style ="Secondary.TButton",command =self .pick_download_dir ).grid (
        row =0 ,column =1
        )
        queue_header =ttk .Frame (right ,style ="Card.TFrame")
        queue_header .grid (row =3 ,column =0 ,sticky ="ew",pady =(16 ,8 ))
        queue_header .columnconfigure (0 ,weight =1 )
        ttk .Label (queue_header ,text ="Очередь",style ="Section.TLabel").grid (row =0 ,column =0 ,sticky ="w")
        ttk .Button (queue_header ,text ="Очистить",style ="Secondary.TButton",command =self .clear_queue ).grid (
        row =0 ,column =1
        )
        self .queue_list =tk .Listbox (
        right ,
        bg ="#0b1220",
        fg ="#e5e7eb",
        selectbackground ="#1d4ed8",
        relief ="flat",
        font =("Следуйте пользовательскому интерфейсу",10 ),
        )
        self .queue_list .grid (row =4 ,column =0 ,sticky ="nsew")
        download_actions =ttk .Frame (right ,style ="Card.TFrame")
        download_actions .grid (row =5 ,column =0 ,sticky ="ew",pady =(12 ,12 ))
        ttk .Button (
        download_actions ,
        text ="Скачать очередь",
        style ="Primary.TButton",
        command =self .start_downloads ,
        ).pack (side ="left",padx =(0 ,8 ))
        ttk .Button (
        download_actions ,
        text ="Удалить выбранное",
        style ="Secondary.TButton",
        command =self .remove_selected_queue_item ,
        ).pack (side ="left")
        ttk .Label (right ,text ="Статус",style ="Section.TLabel").grid (row =6 ,column =0 ,sticky ="w",pady =(0 ,8 ))
        log_frame =tk .Frame (right ,bg ="#0b1220",highlightthickness =1 ,highlightbackground ="#1f2937")
        log_frame .grid (row =7 ,column =0 ,sticky ="nsew")
        log_frame .columnconfigure (0 ,weight =1 )
        log_frame .rowconfigure (0 ,weight =1 )
        self .log_output =tk .Text (
        log_frame ,
        height =10 ,
        wrap ="word",
        bg ="#0b1220",
        fg ="#cbd5e1",
        insertbackground ="#f8fafc",
        relief ="flat",
        state ="disabled",
        font =("Consolas",10 ),
        padx =12 ,
        pady =12 ,
        )
        self .log_output .grid (row =0 ,column =0 ,sticky ="nsew")
        log_scroll =ttk .Scrollbar (
        log_frame ,orient ="vertical",command =self .log_output .yview ,style ="Custom.Vertical.TScrollbar"
        )
        log_scroll .grid (row =0 ,column =1 ,sticky ="ns")
        self .log_output .configure (yscrollcommand =log_scroll .set )
        status_bar =tk .Label (
        self .root ,
        textvariable =self .status_var ,
        anchor ="w",
        bg ="#0b1220",
        fg ="#cbd5e1",
        padx =14 ,
        pady =10 ,
        font =("Следуйте пользовательскому интерфейсу",10 ),
        )
        status_bar .pack (fill ="x",side ="bottom")
    def _load_default_text (self )->None :
        if DEFAULT_TEXT_FILE .exists ():
            self .text_input .delete ("1.0",tk .END )
            self .text_input .insert ("1.0",DEFAULT_TEXT_FILE .read_text (encoding ="utf-8",errors ="ignore"))
            self ._set_status (f"Загружен {DEFAULT_TEXT_FILE .name }")
    def _append_log (self ,message :str )->None :
        self .log_output .configure (state ="normal")
        self .log_output .insert (tk .END ,message +"\n")
        self .log_output .see (tk .END )
        self .log_output .configure (state ="disabled")
    def _set_status (self ,message :str )->None :
        self .status_var .set (message )
        self ._append_log (message )
    def _refresh_summary (self )->None :
        self .summary_var .set (f"Треков: {len (self .tracks )} | В очереди: {len (self .queue_items )}")
    def _refresh_tracks_table (self )->None :
        for item in self .tracks_tree .get_children ():
            self .tracks_tree .delete (item )
        self .track_map .clear ()
        for track in self .tracks :
            item_id =self .tracks_tree .insert (
            "",
            "end",
            values =(
            track .track_id ,
            track .title ,
            track .artist ,
            track .extra_info ,
            track .duration ,
            track .query ,
            ),
            )
            self .track_map [item_id ]=track
        self ._refresh_summary ()
    def load_text_file (self )->None :
        path =filedialog .askopenfilename (
        title ="Выберите текстовый файл",
        filetypes =[("Текстовые файлы","*.текст"),("Все файлы","*.*")],
        )
        if not path :
            return
        file_path =Path (path )
        self .text_input .delete ("1.0",tk .END )
        self .text_input .insert ("1.0",file_path .read_text (encoding ="utf-8",errors ="ignore"))
        self ._set_status (f"Открыт файл: {file_path .name }")
    def build_table (self )->None :
        raw_text =self .text_input .get ("1.0",tk .END ).strip ()
        if not raw_text :
            messagebox .showwarning ("Пустой текст","Добавьте текст со списком треков.")
            return
        self .tracks =parse_tracks (raw_text )
        self ._refresh_tracks_table ()
        self ._set_status (f"Таблица собрана: {len (self .tracks )} треков")
    def export_csv (self )->None :
        if not self .tracks :
            messagebox .showwarning ("Нет данных","Сначала соберите таблицу.")
            return
        path =filedialog .asksaveasfilename (
        title ="Сохранить CSV",
        defaultextension =".csv",
        initialfile =DEFAULT_CSV_FILE .name ,
        filetypes =[("CSV-файлы","*.csv")],
        )
        if not path :
            return
        destination =Path (path )
        export_tracks_to_csv (self .tracks ,destination )
        self ._set_status (f"CSV сохранён: {destination }")
    def _queue_track (self ,track :Track )->bool :
        label =f"{track .title } - {track .artist }".strip (" -")
        if label in self .queue_items :
            return False
        self .queue_items .append (label )
        self .queue_list .insert (tk .END ,label )
        self .download_queue .put (track )
        self ._refresh_summary ()
        return True
    def queue_selected_tracks (self )->None :
        selected =self .tracks_tree .selection ()
        if not selected :
            messagebox .showinfo ("Ничего не выбрано","Выберите хотя бы один трек в таблице.")
            return
        added =0
        for item_id in selected :
            track =self .track_map [item_id ]
            if self ._queue_track (track ):
                added +=1
        self ._set_status (f"В очередь добавлено: {added }")
    def queue_all_tracks (self )->None :
        if not self .tracks :
            messagebox .showwarning ("Нет треков","Сначала соберите таблицу.")
            return
        added =0
        for track in self .tracks :
            if self ._queue_track (track ):
                added +=1
        self ._set_status (f"В очередь добавлено: {added }")
    def clear_queue (self )->None :
        if self .is_downloading :
            messagebox .showwarning ("Идёт загрузка","Очередь нельзя очищать во время скачивания.")
            return
        self .queue_items .clear ()
        self .queue_list .delete (0 ,tk .END )
        self .download_queue =queue .Queue ()
        self ._refresh_summary ()
        self ._set_status ("Очередь очищена")
    def remove_selected_queue_item (self )->None :
        if self .is_downloading :
            messagebox .showwarning ("Идёт загрузка","Во время загрузки удаление из очереди отключено.")
            return
        selection =self .queue_list .curselection ()
        if not selection :
            return
        selected_indices =set (selection )
        labels =list (self .queue_items )
        tracks_to_keep :list [Track ]=[]
        label_index =0
        while not self .download_queue .empty ():
            track =self .download_queue .get ()
            if track is None :
                continue
            if label_index not in selected_indices :
                tracks_to_keep .append (track )
            label_index +=1
        self .queue_items =[label for idx ,label in enumerate (labels )if idx not in selected_indices ]
        self .queue_list .delete (0 ,tk .END )
        for label in self .queue_items :
            self .queue_list .insert (tk .END ,label )
        self .download_queue =queue .Queue ()
        for track in tracks_to_keep :
            self .download_queue .put (track )
        self ._refresh_summary ()
        self ._set_status ("Выбранные элементы удалены из очереди")
    def pick_download_dir (self )->None :
        path =filedialog .askdirectory (title ="Выберите папку для mp3")
        if path :
            self .download_dir_var .set (path )
            self ._set_status (f"Папка сохранения: {path }")
    def start_downloads (self )->None :
        if self .is_downloading :
            messagebox .showinfo ("Загрузка уже запущена","Дождитесь завершения текущей очереди.")
            return
        if not self .queue_items :
            messagebox .showwarning ("Пустая очередь","Добавьте треки в очередь.")
            return
        download_dir =Path (self .download_dir_var .get ()).expanduser ()
        download_dir .mkdir (parents =True ,exist_ok =True )
        try :
            check_ffmpeg ()
        except RuntimeError as error :
            messagebox .showerror ("FFmpeg",str (error ))
            self ._set_status (str (error ))
            return
        self .failed_downloads =[]
        self .is_downloading =True
        self ._set_status (f"Старт загрузки. Треков в очереди: {len (self .queue_items )}")
        worker =threading .Thread (target =self ._download_worker ,args =(download_dir ,),daemon =True )
        worker .start ()
    def _download_worker (self ,download_dir :Path )->None :
        pending_tracks :list [Track ]=[]
        while not self .download_queue .empty ():
            track =self .download_queue .get ()
            if track is not None :
                pending_tracks .append (track )
        for track in pending_tracks :
            label =f"{track .title } - {track .artist }".strip (" -")
            self .worker_events .put (("status",label ,f"Скачивается: {label }"))
            try :
                filename =safe_filename (label or track .title )
                output_template =str (download_dir /f"{filename }.%(ext)s")
                with yt_dlp .YoutubeDL (make_ydl_options (output_template ))as ydl :
                    ydl .download ([track .query ])
                self .worker_events .put (("done",label ,f"Готово: {label }"))
            except Exception as exc :
                self .failed_downloads .append (f"{track .query } :: {exc }")
                self .worker_events .put (("error",label ,f"Ошибка: {label }"))
        if self .failed_downloads :
            FAILED_LOG .write_text ("\n".join (self .failed_downloads ),encoding ="utf-8")
        elif FAILED_LOG .exists ():
            FAILED_LOG .unlink ()
        self .worker_events .put (("complete","","Загрузка очереди завершена"))
    def _process_worker_events (self )->None :
        try :
            while True :
                event_type ,label ,message =self .worker_events .get_nowait ()
                if event_type =="status":
                    self .status_var .set (message )
                    self ._append_log (message )
                elif event_type in {"done","error"}:
                    self .status_var .set (message )
                    self ._append_log (message )
                    if self .queue_items and self .queue_items [0 ]==label :
                        self .queue_items .pop (0 )
                        self .queue_list .delete (0 )
                    else :
                        for index ,item in enumerate (self .queue_items ):
                            if item ==label :
                                self .queue_items .pop (index )
                                self .queue_list .delete (index )
                                break
                    self ._refresh_summary ()
                elif event_type =="complete":
                    self .is_downloading =False
                    final_message =message
                    if self .failed_downloads :
                        final_message =f"{message }. Ошибки сохранены в {FAILED_LOG .name }"
                    self .status_var .set (final_message )
                    self ._append_log (final_message )
                    self ._refresh_summary ()
        except queue .Empty :
            pass
        self .root .after (150 ,self ._process_worker_events )
def main ()->None :
    root =tk .Tk ()
    MusicApp (root )
    root .mainloop ()
if __name__ =="__main__":
    main ()