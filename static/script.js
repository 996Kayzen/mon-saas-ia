document.addEventListener('DOMContentLoaded', () => {
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const chatBox = document.getElementById('chat-box');

    let conversationHistory = [];

    function appendMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return messageDiv;
    }

    async function handleSendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        appendMessage(message, 'user');
        conversationHistory.push({ role: "user", content: message });
        userInput.value = '';

        const loadingMessage = appendMessage('Réflexion en cours...', 'bot');

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ history: conversationHistory })
            });

            const data = await response.json();

            if (data.reply) {
                loadingMessage.textContent = data.reply;
                conversationHistory.push({ role: "assistant", content: data.reply });
            } else if (data.error) {
                loadingMessage.textContent = "Erreur : " + data.error;
                conversationHistory.pop();
            }
        } catch (error) {
            loadingMessage.textContent = "Impossible de contacter le serveur.";
            console.error('Erreur:', error);
            conversationHistory.pop();
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    }

    sendBtn.addEventListener('click', handleSendMessage);

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleSendMessage();
        }
    });
});