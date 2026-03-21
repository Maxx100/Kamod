# Kamod
MegaKamod

## Сервисы

- Database service: `services/database/README.md`

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
