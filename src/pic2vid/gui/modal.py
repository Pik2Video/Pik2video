


[RAM: 0 KB]   [TIME: 00:00:00]   [SHOTS: 0]

# Открыть главное окно (IDLE)

python test.py idle

# Открыть окно подготовки видео

python test.py prep_video
python test.py prep_screen

# Режим записи (для DEV, без фактической записи)
python test.py recording_video
python test.py recording_screen

# Финализация видео/экрана
python test.py review_video
python test.py review_screen



gui
│
├─ components_settings - каталог для хранения настроей
│   │
│   ├─ setting_row.py - сборщик строки для настроек (текст/виджет). 
│   │      └─ SettingRow
│   │
│   │
│   ├─ global_settings.py - глобальные настройки приложения .
│   │      ├─ LanguageSetting
│   │      ├─ TextSizeSetting
│   │      ├─ TooltipsSetting
│   │      └─ StartDelaySetting
│   │
│   │
│   ├─ record_settings.py - предварительные настройки перед записи видео
│   │      └─ FpsSwitcher
│   │
│   ├─ screen_settings.py - предварительные настройки перед перед screen записи
│   │      └─ CapturePerMinuteInput
│   │
│   │
│   └─ common_settings.py общие предварительные настройки для записи в обеих сценариях
│          ├─ QualitySwitcher
│          └─ TimerInput








scripts/
├── generate_icon.py         
├── elements/
│   ├── __init__.py          
│   ├── monitor.py            
│   ├── buttons.py            
│   ├── timer.py              
│   └── utils.py              
└── assets/
    ├── fonts/                
    └── templates/            