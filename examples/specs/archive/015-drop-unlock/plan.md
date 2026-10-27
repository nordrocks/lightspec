# 015-drop-unlock: план

## Техническое решение

- обработчик разблокировки и письмо со ссылкой удаляются

## Задачи

### [x] Задача 001: Удаление разблокировки по ссылке
Реализует: req:AUTH-007, req:AUTH-003, contract:public-api.unlock, contract:public-api.unlock-input
Документация: doc:auth/login, doc:_project/deploy
Проверка: тесты сценариев req:AUTH-003

- Действие: убрать операцию и письмо
  - Файлы:
    - DEL `src/api/unlock.py`
    - DEL `src/auth/unlock_token.py`
