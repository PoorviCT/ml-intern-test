import os
import math
import random
import argparse

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    DataCollatorWithPadding,
    TrainingArguments,
    Trainer,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model_name_or_path', type=str, default='Qwen/Qwen2.5-0.5B')
    parser.add_argument('--dataset_name', type=str, default='fancyzhx/ag_news')
    parser.add_argument('--output_dir', type=str, default='./qwen-agnews-out')
    parser.add_argument('--max_length', type=int, default=128)
    parser.add_argument('--per_device_train_batch_size', type=int, default=16)
    parser.add_argument('--per_device_eval_batch_size', type=int, default=32)
    parser.add_argument('--learning_rate', type=float, default=2e-5)
    parser.add_argument('--num_train_epochs', type=int, default=1)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--logging_steps', type=int, default=20)
    parser.add_argument('--eval_steps', type=int, default=200)
    args = parser.parse_args()

    # Determinism
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    dataset = load_dataset(args.dataset_name)

    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=True)

    def preprocess(batch):
        return tokenizer(
            batch['text'],
            truncation=True,
            max_length=args.max_length,
        )

    # Remove columns except label and encoded features
    tokenized = dataset.map(preprocess, batched=True, remove_columns=['text'])

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name_or_path,
        num_labels=4,
    )

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = logits.argmax(axis=-1)
        acc = (preds == labels).mean()
        return {'accuracy': float(acc)}

    # Ensure plain-text logs without tqdm (trainer still uses tqdm internally)
    # We disable tqdm and use logging_strategy="steps".
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        per_device_eval_batch_size=args.per_device_eval_batch_size,
        num_train_epochs=args.num_train_epochs,
        eval_strategy='steps',
        eval_steps=args.eval_steps,
        logging_strategy='steps',
        logging_steps=args.logging_steps,
        logging_first_step=True,
        save_strategy='no',
        seed=args.seed,
        report_to=[],
        disable_tqdm=True,
        bf16=torch.cuda.is_available(),
        gradient_checkpointing=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized['train'],
        eval_dataset=tokenized['test'],
        tokenizer=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    train_result = trainer.train()
    metrics = train_result.metrics

    # Print final metrics
    print('FINAL_TRAIN_METRICS', metrics)
    eval_metrics = trainer.evaluate()
    print('FINAL_EVAL_METRICS', eval_metrics)


if __name__ == '__main__':
    main()
