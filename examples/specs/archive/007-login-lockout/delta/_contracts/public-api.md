## public-api.login
Изменение: ADDED
Источник: None
Причина: None
Тип: операция
Выход: contract:public-api.session

Вход по логину и паролю.

### Гарантии

- идемпотентность: нет

### Формат

- вызов: `POST /login`

## public-api.refresh
Изменение: ADDED
Источник: None
Причина: None
Тип: протокол

Продление сессии без повторного ввода пароля.

### Шаги

1. вызов с `token` вернул HTTP 401
2. клиент отправляет `refreshToken` на `POST /refresh` и получает новую contract:public-api.session
3. `POST /refresh` вернул HTTP 401 — клиент снова вызывает contract:public-api.login

## public-api.session
Изменение: ADDED
Источник: None
Причина: None
Тип: модель

Открытая сессия пользователя.

### Поля

| Поле | Тип | Формат | Обязательно | Описание |
|---|---|---|---|---|
| token | string | JWT | да | для вызовов от имени пользователя |
| refreshToken | string | — | да | для contract:public-api.refresh |
