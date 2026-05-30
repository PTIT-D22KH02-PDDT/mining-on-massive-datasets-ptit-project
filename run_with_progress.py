#!/usr/bin/env python3
"""
Runner script for MBA training with progress tracking
Prints progress at every step to avoid black box execution
"""

import sys
import os
import subprocess
import time
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('mba_training_progress.log')
    ]
)
logger = logging.getLogger(__name__)

def print_header(text):
    """Print formatted header"""
    logger.info("\n" + "="*80)
    logger.info(text.center(80))
    logger.info("="*80 + "\n")

def print_step(step_num, description):
    """Print step number and description"""
    logger.info(f"\n[STEP {step_num}] {description}")
    logger.info("-" * 80)

def main():
    print_header("MBA Training Runner with Progress Tracking")
    
    # Training parameters
    params = {
        'datadir': '/kaggle/working/data',
        'folder': '/kaggle/working/output',
        'dataset': 'otto',
        'train_method': 'pre',
        'model': 'MF',
        'pretrain_model': 'MF',
        'lambda0': '1e-4',
        'pretrain_early_stop_rounds': '20',
        'idx': '0',
    }
    
    # Check if we're running locally or on Kaggle
    script_path = '/kaggle/input/datasets/hngphongkiu/rs-mba/main.py'
    if not os.path.exists(script_path):
        script_path = './MBA/main.py'
    
    print_step(1, "Validating training parameters")
    logger.info(f"Script path: {script_path}")
    for key, value in params.items():
        logger.info(f"  {key}: {value}")
    
    if not os.path.exists(script_path):
        logger.error(f"ERROR: Script not found at {script_path}")
        return 1
    
    print_step(2, "Building command")
    cmd = [
        'python', '-u', script_path,
        '--datadir', params['datadir'],
        '--folder', params['folder'],
        '--dataset', params['dataset'],
        '--train_method', params['train_method'],
        '--model', params['model'],
        '--pretrain_model', params['pretrain_model'],
        '--lambda0', params['lambda0'],
        '--pretrain_early_stop_rounds', params['pretrain_early_stop_rounds'],
        '--idx', params['idx'],
    ]
    
    logger.info("Full command:")
    logger.info(" ".join(cmd))
    
    print_step(3, "Starting training process")
    logger.info(f"Start time: {datetime.now()}")
    
    try:
        # Run training with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1  # Line buffered
        )
        
        # Stream output in real-time
        for line in process.stdout:
            line = line.rstrip()
            if line:
                logger.info(f"[TRAINING] {line}")
        
        # Wait for process to complete
        return_code = process.wait()
        
        print_step(4, "Training completed")
        logger.info(f"End time: {datetime.now()}")
        logger.info(f"Return code: {return_code}")
        
        if return_code == 0:
            logger.info("✓ Training completed successfully!")
        else:
            logger.error(f"✗ Training failed with return code {return_code}")
        
        return return_code
        
    except KeyboardInterrupt:
        logger.warning("\nTraining interrupted by user")
        process.terminate()
        return 1
    except Exception as e:
        logger.error(f"Error during training: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    print_header(f"Final Status: {'SUCCESS' if exit_code == 0 else 'FAILED'}")
    sys.exit(exit_code)
