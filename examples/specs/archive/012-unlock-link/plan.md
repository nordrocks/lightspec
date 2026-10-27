# 012-unlock-link: план

## Техническое решение

- токен хранится в основной базе: adr:unlock-token-storage

## Задачи

### [x] Задача 001: Токен разблокировки
Реализует: req:AUTH-007, req:AUTH-003
Документация: doc:auth/login, doc:_project/deploy
Проверка: тесты сценариев req:AUTH-007

- Действие: выдача токена
  - Файлы:
    - ADD `src/auth/unlock_token.py`

### [x] Задача 002: Операция разблокировки
Реализует: contract:public-api.unlock, contract:public-api.unlock-input
Проверка: контрактные тесты contract:public-api.unlock

- Действие: операция
