# Kamod
MegaKamod

## Локальная PostgreSQL БД

В `docker-compose.yml` данные PostgreSQL теперь сохраняются в папку проекта:

`./data/postgres`

Внутри контейнера это смонтировано в:

`/var/lib/postgresql/data`

Если раньше БД поднималась через именованный Docker volume, данные автоматически в новую папку не переедут. Для нового запуска достаточно создать директорию `data/postgres` и заново поднять `postgres`.

>  ### **Использование логгера**<br>

Вот так инициализируем логгер в самом начале, используя конфигуратор из core/ (не забудьте в свой `.env` поместить поле `LOG_LEVEL`, равное `DEBUG` или `INFO`)
```
from core.log_config import setup_logging
import logging

# Инициализируем логирование ОДИН раз при старте приложения
setup_logging()

# Получаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Используем логгер
logger.debug("Дебаг")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
logger.critical("Критическая ошибка")
```

Во всех остальных файлах достаточно просто использовать логгер
```
import logging

# Просто получаем логгер (setup_logging уже вызван в main.py)
logger = logging.getLogger(__name__)

logger.info("Все запишется в один файл")
```
