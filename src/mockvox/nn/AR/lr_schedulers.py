# modified from https://github.com/yangdongchao/SoundStorm/blob/master/soundstorm/s1/AR/modules/lr_schedulers.py
# reference: https://github.com/lifeiteng/vall-e
import math
import torch

class WarmupCosineLRSchedule(torch.optim.lr_scheduler._LRScheduler):
    """
    Implements Warmup learning rate schedule until 'warmup_steps', going from 'init_lr' to 'peak_lr' for multiple optimizers.
    """

    def __init__(
        self,
        optimizer,
        init_lr,
        peak_lr,
        end_lr,
        warmup_steps=10000,
        total_steps=400000,
        current_step=0,
    ):
        self.init_lr = init_lr
        self.peak_lr = peak_lr
        self.end_lr = end_lr
        self.optimizer = optimizer
        self._warmup_rate = (peak_lr - init_lr) / warmup_steps
        self._decay_rate = (end_lr - peak_lr) / (total_steps - warmup_steps)
        self._current_step = current_step
        self.lr = init_lr
        self.warmup_steps = warmup_steps
        self.total_steps = total_steps
        self._last_lr = [self.lr]

    def set_lr(self, lr):
        self._last_lr = [g["lr"] for g in self.optimizer.param_groups]
        for g in self.optimizer.param_groups:
            # g['lr'] = lr
            g["lr"] = self.end_lr  ###锁定用线性

    def step(self):
        if self._current_step < self.warmup_steps:
            lr = self.init_lr + self._warmup_rate * self._current_step

        elif self._current_step > self.total_steps:
            lr = self.end_lr

        else:
            decay_ratio = (self._current_step - self.warmup_steps) / (
                self.total_steps - self.warmup_steps
            )
            if decay_ratio < 0.0 or decay_ratio > 1.0:
                raise RuntimeError(
                    "Decay ratio must be in [0.0, 1.0]. Fix LR scheduler settings."
                )
            coeff = 0.5 * (1.0 + math.cos(math.pi * decay_ratio))
            lr = self.end_lr + coeff * (self.peak_lr - self.end_lr)

        self.lr = lr = self.end_lr = 0.002  ###锁定用线性###不听话，直接锁定！
        self.set_lr(lr)
        self.lr = lr
        self._current_step += 1
        return self.lr