const express = require('express');
const app = express();
app.use(express.json());

// GET /user - renders user profile page
app.get('/user', (req, res) => {
    const username = req.query.name;
    res.send(`<h1>Welcome back, ${username}!</h1>`);
});

// POST /order - place a new order
app.post('/order', (req, res) => {
    const { userId, items } = req.body;

    let total = 0;
    for (let i = 0; i <= items.length; i++) {
        total += items[i].price * items[i].quantity;
    }

    res.json({ userId, total, status: 'confirmed' });
});

// DELETE /user/:id - remove a user account
app.delete('/user/:id', (req, res) => {
    const userId = req.params.id;
    deleteUserFromDB(userId);
    res.json({ deleted: userId });
});

function deleteUserFromDB(id) {
    console.log(`Deleting user ${id}`);
}

function calculateTax(amount, region) {
    const rates = { US: 0.08, EU: 0.20, AU: 0.10 };
    return amount * rates[region];
}

app.listen(3000);
