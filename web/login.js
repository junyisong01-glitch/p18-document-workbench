'use strict';
const form = document.querySelector('#login');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const message = document.querySelector('#message');
  button.disabled = true;
  message.textContent = '正在登录…';
  try {
    const fields = new FormData(form);
    const response = await fetch('/api/library/login', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-P18-Client': 'workbench'},
      body: JSON.stringify({username: fields.get('username'), password: fields.get('password')})
    });
    form.elements.password.value = '';
    if (!response.ok) {
      const result = await response.json();
      message.textContent = typeof result.detail === 'string' ? result.detail : '登录失败，请检查账号和密码。';
      return;
    }
    location.assign('/library/');
  } catch { message.textContent = '连接失败，请稍后重试。'; }
  finally { button.disabled = false; }
});
