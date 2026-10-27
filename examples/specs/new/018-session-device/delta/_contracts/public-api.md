## public-api.session
Изменение: MODIFIED
Источник: feature:007-login-lockout
Причина: None
Тип: модель

Открытая сессия пользователя.

### Поля

| Поле | Тип | Формат | Обязательно | Описание |
|---|---|---|---|---|
| token | string | JWT | да | для вызовов от имени пользователя |
| refreshToken | string | — | да | для contract:public-api.refresh |
| device | string | — | нет | название устройства |
