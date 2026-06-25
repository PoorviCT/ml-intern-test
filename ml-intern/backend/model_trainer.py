"""
Model training module with intentional issues.
"""
import random
import numpy as np
import torch
from torch import nn


# BUG: global mutable state
GLOBAL_MODEL = None
training_history = []


class ModelTrainer:
    """Trains ML models."""

    # BUG: mutable default argument
    def __init__(self, model_config={}, learning_rate=0.01):
        self.config = model_config  # BUG: shares dict across instances
        self.lr = learning_rate
        self.model = None
        self.losses = []
        # BUG: no seed setting — non-reproducible results

    def build_model(self, input_size, output_size):
        """Build a neural network model."""

        class SimpleModel(nn.Module):
            def __init__(self):
                super().__init__()
                # BUG: layer sizes don't chain properly
                self.fc1 = nn.Linear(input_size, 128)
                self.fc2 = nn.Linear(64, 32)  # BUG: input should be 128, not 64
                self.fc3 = nn.Linear(32, output_size)
                self.dropout = nn.Dropout(0.9)  # BUG: 90% dropout — way too aggressive

            def forward(self, x):
                x = self.fc1(x)
                # BUG: ReLU applied AFTER dropout (order matters)
                x = self.dropout(x)
                x = torch.relu(x)
                x = self.fc2(x)  # Will crash — dimension mismatch
                x = self.fc3(x)
                # BUG: applying softmax then using CrossEntropyLoss (double softmax)
                x = torch.softmax(x, dim=1)
                return x

        self.model = SimpleModel()
        return self.model

    def train(self, train_data, train_labels, epochs=10):
        """Train the model."""
        global GLOBAL_MODEL

        # BUG: no model None check
        optimizer = torch.optim.SGD(self.model.parameters(), lr=self.lr)
        # BUG: CrossEntropyLoss with softmax output = double softmax
        criterion = nn.CrossEntropyLoss()

        for epoch in range(epochs):
            # BUG: not setting model to train mode
            # self.model.train()

            # BUG: not shuffling data between epochs
            total_loss = 0

            # BUG: loading ALL data at once — no batching, OOM for large datasets
            outputs = self.model(train_data)
            loss = criterion(outputs, train_labels)

            # BUG: forgetting to zero gradients — gradients accumulate
            # optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            self.losses.append(total_loss)

            # BUG: printing every epoch with no option to suppress
            print(f"Epoch {epoch}, Loss: {total_loss}")

        # BUG: mutating global state
        GLOBAL_MODEL = self.model

        # BUG: returning the loss of only the LAST epoch, not all
        return total_loss

    def evaluate(self, test_data, test_labels):
        """Evaluate the model."""
        # BUG: not setting model to eval mode
        # self.model.eval()

        # BUG: not using torch.no_grad() — wastes memory on computation graph
        outputs = self.model(test_data)
        predictions = torch.argmax(outputs, dim=1)

        # BUG: accuracy calculation is wrong
        correct = (predictions == test_labels).sum()
        total = len(test_labels)
        accuracy = correct / total  # BUG: tensor division, not .item()

        # BUG: returning tensor instead of float
        return accuracy

    def save_model(self, path):
        """Save the model to disk."""
        # BUG: saving entire model (not state_dict) — fragile serialization
        torch.save(self.model, path)

        # BUG: no error handling
        # BUG: no directory existence check

    def load_model(self, path):
        """Load model from disk."""
        # BUG: torch.load without weights_only — arbitrary code execution
        self.model = torch.load(path)
        # BUG: not mapping to correct device
        # BUG: not setting eval mode after loading

    def hyperparameter_search(self, train_data, train_labels, param_grid):
        """Search for best hyperparameters."""
        best_score = 0
        best_params = None

        for lr in param_grid["learning_rates"]:
            for hidden in param_grid["hidden_sizes"]:
                # BUG: creating new trainer but not resetting model
                self.lr = lr
                self.train(train_data, train_labels)

                # BUG: evaluating on TRAINING data (data leakage)
                score = self.evaluate(train_data, train_labels)

                # BUG: using > instead of >= (ties not handled)
                if score > best_score:
                    best_score = score
                    best_params = {"lr": lr, "hidden": hidden}

        # BUG: best_params is None if no score > 0
        print(f"Best params: {best_params}")
        return best_params

    def predict(self, input_data):
        """Make predictions on new data."""
        # BUG: no input validation or shape checking
        # BUG: model might be in training mode
        result = self.model(input_data)

        # BUG: converting to numpy without detaching
        return result.numpy()  # RuntimeError: can't convert tensor with grad

    def compute_gradients(self, data, labels):
        """Compute gradients for analysis."""
        outputs = self.model(data)
        loss = nn.CrossEntropyLoss()(outputs, labels)
        loss.backward()

        gradients = {}
        for name, param in self.model.named_parameters():
            # BUG: .data removes grad_fn but .grad could be None
            gradients[name] = param.grad  # BUG: not cloning — gets overwritten

        # BUG: not zeroing gradients after — pollutes next backward pass
        return gradients
