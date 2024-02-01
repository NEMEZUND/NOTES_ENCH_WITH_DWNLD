import PySimpleGUI as sg
import psycopg2
from datetime import datetime
from PIL import Image, ImageTk, ImageSequence
import io
from base64 import b64encode
import os
import pyperclip

class GifViewer:
    def __init__(self, gif_path):
        self.gif_path = gif_path
        self.gif = None
        self.load_gif()

    def load_gif(self):
        try:
            self.gif = Image.open(self.gif_path)
            self.frames = self.get_gif_frames()
        except Exception as e:
            sg.popup_error(f"Error loading GIF: {e}")

    def get_gif_frames(self):
        try:
            frames = [ImageTk.PhotoImage(img) for img in ImageSequence.Iterator(self.gif)]
            return frames
        except Exception as e:
            sg.popup_error(f"Error extracting frames from GIF: {e}")
            return []

    def play_gif(self, window, key):
        for frame in self.frames:
            event, values = window.read(timeout=100)  # Adjust timeout as needed
            if event == sg.WINDOW_CLOSED:
                break
            window[key].update(data=b64encode(self.image_to_bytes(frame)).decode(), animation_time=100)

    def image_to_bytes(self, image):
        img_byte_array = io.BytesIO()
        image.save(img_byte_array, format="GIF")
        return img_byte_array.getvalue()

# Подключение к базе данных PostgreSQL
conn = psycopg2.connect(
    dbname='Notes',
    user='postgres',
    password='Pwd000',
    host='localhost',
    port='5432'
)

# Создание таблицы для заметок
create_table_query = """
CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image BYTEA
);
"""
with conn.cursor() as cursor:
    cursor.execute(create_table_query)
conn.commit()

# Функция для вставки заметки в базу данных
def insert_note(title, content, image_path=None):
    if not title.strip():
        sg.popup('Title cannot be empty!')
        return None

    image_bytes = image_to_bytes(image_path) if image_path else None
    insert_query = """
    INSERT INTO notes (title, content, created_at, updated_at, image)
    VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)
    RETURNING id, created_at, updated_at;
    """
    with conn.cursor() as cursor:
        cursor.execute(insert_query, (title, content, psycopg2.Binary(image_bytes)))
        result = cursor.fetchone()
    conn.commit()
    return result

# Функция для обновления заметки в базе данных
def update_note(note_id, title, content, image_path, paste_from_clipboard=False):
    image_bytes = image_to_bytes(image_path) if image_path else None

    if paste_from_clipboard:
        clipboard_content = pyperclip.paste()
        content += clipboard_content

    update_query = """
    UPDATE notes
    SET title = %s, content = %s, image = %s, updated_at = CURRENT_TIMESTAMP
    WHERE id = %s
    RETURNING updated_at;
    """
    with conn.cursor() as cursor:
        cursor.execute(update_query, (title, content, psycopg2.Binary(image_bytes), note_id))
        updated_at = cursor.fetchone()[0]
    conn.commit()

    window_main.write_event_value('update_note', (note_id, title, content, image_path, updated_at))

    return updated_at

# Функция для отображения полной заметки в отдельном окне
def display_full_note_window(note):
    note_id, title, content, created_at, updated_at, image_bytes = note
    created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
    updated_at_str = updated_at.strftime('%Y-%m-%d %H:%M:%S') if updated_at else ''

    image_data = b64encode(image_bytes).decode() if image_bytes else None
    image_elem = sg.Image(data=image_data, key='image_display', enable_events=True)

    layout_full_note = [
        [sg.Text(f'Title: {title}')],
        [sg.Multiline(f'{content}', size=(40, 10), key='content_display', disabled=True)],
        [sg.Text(f'Created At: {created_at_str}')],
        [sg.Text(f'Updated At: {updated_at_str}')],
        [image_elem],
        [sg.Button('Download Image'), sg.Button('Copy Text'), sg.Button('Close')],
    ]

    window_full_note = sg.Window(f'Full Note - ID: {note_id}', layout_full_note, resizable=True)

    while True:
        event_full_note, _ = window_full_note.read()

        if event_full_note == sg.WINDOW_CLOSED or event_full_note == 'Close':
            break
        elif event_full_note == 'Download Image' and image_bytes:
            download_path = sg.popup_get_file('Save Image As', save_as=True, default_extension=".png")
            if download_path:
                with open(download_path, 'wb') as f:
                    f.write(image_bytes)
                sg.popup(f'Image saved to {download_path}')
        elif event_full_note == 'Copy Text':
            sg.popup_ok('Text copied to clipboard!')
            pyperclip.copy(content)

    window_full_note.close()

# Функция для отображения заметок с учетом сокращенного текста
def display_notes_with_pagination(notes):
    if not notes:
        sg.popup('No notes found!')
        return

    page_size = 2
    current_page = 1

    while True:
        notes_to_display = notes[(current_page - 1) * page_size:current_page * page_size]

        layout = []
        for note in notes_to_display:
            note_id, title, content, created_at, updated_at, image_bytes = note
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
            updated_at_str = updated_at.strftime('%Y-%m-%d %H:%M:%S') if updated_at else ''

            short_content = content[:200] + '...' if len(content) > 200 else content

            layout.append([sg.Text(f'Title: {title}')])
            layout.append([sg.Multiline(f'{short_content}', size=(40, 5), key='content_display', disabled=True)])
            layout.append([sg.Text(f'Created At: {created_at_str}')])
            layout.append([sg.Text(f'Updated At: {updated_at_str}')])
            layout.append([sg.Button(f'Edit {note_id}'), sg.Button(f'Delete {note_id}'), sg.Button(f'Read More {note_id}')])

        layout.append([sg.Text(f'Page {current_page}')])
        layout.append([sg.Button('Prev Page'), sg.Button('Next Page')])

        window_notes = sg.Window('Notes', layout, resizable=True)

        event, values = window_notes.read()

        if event == sg.WINDOW_CLOSED:
            break
        elif event == 'Prev Page':
            if current_page > 1:
                current_page -= 1
        elif event == 'Next Page':
            if current_page < len(notes) // page_size + 1:
                current_page += 1
        elif event.startswith('Edit'):
            note_id = int(event.split()[-1])
            edit_note_window(note_id)
        elif event.startswith('Delete'):
            note_id = int(event.split()[-1])
            delete_note(note_id)
            sg.popup(f'Note {note_id} deleted!')
            window_notes.close()
            break
        elif event.startswith('Read More'):
            note_id = int(event.split()[-1])
            full_note = [note for note in notes if note[0] == note_id][0]
            display_full_note_window(full_note)

        window_notes.close()

# Функция для редактирования заметок с учетом сокращенного текста
def edit_note_window(note_id):
    note_query = """
    SELECT title, content, image
    FROM notes
    WHERE id = %s;
    """
    with conn.cursor() as cursor:
        cursor.execute(note_query, (note_id,))
        result = cursor.fetchone()

    title, content, image_bytes = result
    image_path = None
    if image_bytes:
        temp_image_path = f'temp_image_{note_id}.png'
        with open(temp_image_path, 'wb') as f:
            Image.open(io.BytesIO(image_bytes)).convert('RGBA').save(f, format='PNG')
        image_path = temp_image_path

    short_content = content[:200] + '...' if len(content) > 200 else content

    layout_edit = [
        [sg.Text('Title:'), sg.InputText(default_text=title, key='title')],
        [sg.Text('Content:'), sg.Multiline(default_text=short_content, size=(40, 5), key='content', enable_events=True)],
        [sg.Text('Image:'), sg.InputText(default_text=image_path, key='image_path'), sg.FileBrowse()],
        [sg.Button('Update'), sg.Button('Cancel')],
    ]

    window_edit = sg.Window(f'Edit Note ID: {note_id}', layout_edit, resizable=True)

    while True:
        event_edit, values_edit = window_edit.read()

        if event_edit == sg.WINDOW_CLOSED or event_edit == 'Cancel':
            break
        elif event_edit == 'Update':
            title_edit = values_edit['title']
            content_edit = values_edit['content']
            image_path_edit = values_edit['image_path']

            update_note(note_id, title_edit, content_edit, image_path_edit)

            sg.popup(f'Note {note_id} updated!')
            window_edit.close()
            break

    window_edit.close()
    if image_path:
        os.remove(image_path)

# Функция для преобразования изображения в байты
def image_to_bytes(image_path):
    if image_path and image_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
        if image_path.lower().endswith(('.jpg', '.jpeg')):
            # Convert JPEG to PNG
            img = Image.open(image_path).convert('RGBA')
            png_byte_array = io.BytesIO()
            img.save(png_byte_array, format='PNG')
            return png_byte_array.getvalue()
        else:
            with open(image_path, 'rb') as f:
                return f.read()
    elif image_path:
        sg.popup('Invalid image format! Please select a valid image file.')
        return None
    else:
        return None

# Функция для удаления заметки
def delete_note(note_id):
    delete_query = """
    DELETE FROM notes
    WHERE id = %s;
    """
    with conn.cursor() as cursor:
        cursor.execute(delete_query, (note_id,))
    conn.commit()

# Функция для поиска заметок с учетом сокращенного отображения текста
def search_notes(search_type, search_value):
    if search_type == 'Date':
        search_query = """
        SELECT id, title, content, created_at, updated_at, image
        FROM notes
        WHERE created_at::date = %s::date OR updated_at::date = %s::date
        """
        params = (search_value, search_value)
    elif search_type == 'Title':
        search_query = """
        SELECT id, title, content, created_at, updated_at, image
        FROM notes
        WHERE title ILIKE %s
        """
        params = (f"%{search_value}%",)
    elif search_type == 'Text':
        search_query = """
        SELECT id, title, content, created_at, updated_at, image
        FROM notes
        WHERE content ILIKE %s
        """
        params = (f"%{search_value}%",)
    else:
        return []

    with conn.cursor() as cursor:
        cursor.execute(search_query, params)
        return cursor.fetchall()

# Графический интерфейс PySimpleGUI
sg.theme('LightGrey1')

layout_main = [
    [sg.Text('Title:'), sg.InputText(key='title')],
    [sg.Text('Content:'), sg.Multiline(key='content', size=(40, 5), enable_events=True)],
    [sg.Text('Image:'), sg.InputText(key='image_path'), sg.FileBrowse()],
    [sg.Button('Add'), sg.Button('Search'), sg.Button('View All')],
]

window_main = sg.Window('Note App', layout_main, resizable=True)

while True:
    event_main, values_main = window_main.read()

    if event_main == sg.WINDOW_CLOSED:
        break
    elif event_main == 'Add':
        title = values_main['title']
        content = values_main['content']
        image_path = values_main['image_path']
        result = insert_note(title, content, image_path)
        if result:
            note_id, created_at, updated_at = result
            sg.popup(f'Note added! ID: {note_id}\nCreated At: {created_at}\nUpdated At: {updated_at}')
    elif event_main == 'Search':
        search_layout = [
            [sg.Text('Select Search Type:')],
            [sg.Radio('Date', 'SEARCH_TYPE', default=True, key='search_type_date'),
             sg.Radio('Title', 'SEARCH_TYPE', key='search_type_title'),
             sg.Radio('Text', 'SEARCH_TYPE', key='search_type_text')],
            [sg.Text('Enter Search Value:')],
            [sg.InputText(key='search_value')],
            [sg.Button('Search'), sg.Button('Cancel')],
        ]

        window_search = sg.Window('Search Notes', search_layout)

        while True:
            event_search, values_search = window_search.read()

            if event_search == sg.WINDOW_CLOSED or event_search == 'Cancel':
                break
            elif event_search == 'Search':
                search_type_date = values_search['search_type_date']
                search_type_title = values_search['search_type_title']
                search_type_text = values_search['search_type_text']

                if search_type_date:
                    search_type = 'Date'
                elif search_type_title:
                    search_type = 'Title'
                elif search_type_text:
                    search_type = 'Text'
                else:
                    sg.popup('Please select a search type!')
                    continue

                search_value = values_search['search_value']

                notes = search_notes(search_type, search_value)
                display_notes_with_pagination(notes)
                window_search.close()
                break

        window_search.close()
    elif event_main == 'View All':
        notes_query = """
        SELECT id, title, content, created_at, updated_at, image
        FROM notes;
        """
        with conn.cursor() as cursor:
            cursor.execute(notes_query)
            notes = cursor.fetchall()
        display_notes_with_pagination(notes)

# Закрытие соединения с базой данных
conn.close()
