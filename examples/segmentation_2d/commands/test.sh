#!/bin/bash

python -m manafaln.apps.validate \
    -c configs/test.yaml \
    -f lightning_logs/version_$1/checkpoints/best_model.ckpt