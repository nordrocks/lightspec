# public-api: контракт
Источник: feature:007-login-lockout

Мобильное и веб-приложение. HTTPS, JSON, базовый URL `https://api.example.com/v1`.

## public-api.login
Источник: feature:007-login-lockout
Тип: операция
Выход: contract:public-api.session

Вход по логину и паролю.

### Гарантии

- идемпотентность: нет

### Формат

- вызов: `POST /login`

## public-api.refresh
Источник: feature:007-login-lockout
Тип: протокол

Продление сессии без повторного ввода пароля.

### Шаги

1. вызов с `token` вернул HTTP 401
2. клиент отправляет `refreshToken` на `POST /refresh` и получает новую contract:public-api.session
3. `POST /refresh` вернул HTTP 401 — клиент снова вызывает contract:public-api.login

## public-api.session
Источник: feature:007-login-lockout
Тип: модель

Открытая сессия пользователя.

### Поля

| Поле | Тип | Формат | Обязательно | Описание |
|---|---|---|---|---|
| token | string | JWT | да | для вызовов от имени пользователя |
| refreshToken | string | — | да | для contract:public-api.refresh |
