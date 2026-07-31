document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatBox = document.getElementById('chat-box');

    // Tableau pour conserver l'historique complet de la discussion
    let conversationHistory = [];

    function appendMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return messageDiv;
    }

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const message = userInput.value.trim();
        if (!message) return;

        // 1. Afficher le message de l'utilisateur à l'écran
        appendMessage(message, 'user');
        
        // 2. Ajouter le message de l'utilisateur dans la mémoire globale
        conversationHistory.push({ role: "user", content: message });

        userInput.value = '';

        const loadingMessage = appendMessage('Réflexion en cours...', 'bot');

        try {
            // 3. Envoyer tout l'historique de discussion à Flask au lieu d'un simple message
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ history: conversationHistory })
            });

            const data = await response.json();

            if (data.reply) {
                loadingMessage.textContent = data.reply;
                // 4. Enregistrer la réponse de l'IA dans la mémoire globale
                conversationHistory.push({ role: "assistant", content: data.reply });
            } else if (data.error) {
                loadingMessage.textContent = "Erreur : " + data.error;
                // En cas d'erreur de réponse API, on retire le dernier message envoyé pour ne pas corrompre l'historique
                conversationHistory.pop();
            }
        } catch (error) {
            loadingMessage.textContent = "Impossible de contacter le serveur.";
            console.error('Erreur:', error);
            // En cas d'erreur réseau, on retire aussi le dernier message de l'historique
            conversationHistory.pop();
        }

        chatBox.scrollTop = chatBox.scrollHeight;
    });
});