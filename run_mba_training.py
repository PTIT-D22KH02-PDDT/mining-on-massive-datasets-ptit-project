#!/usr/bin/env python3
"""
Complete MBA Training Runner with Progress Tracking
Runs the MBA training script with real-time progress monitoring
"""

import sys
import os
import subprocess
import argparse
import json
from pathlib import Path
from datetime import datetime

class Colors:
    """ANSI color codes"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.ENDC}\n")

def print_step(step_num, description):
    """Print step with formatting"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}[STEP {step_num}] {description}{Colors.ENDC}")
    print(f"{Colors.BLUE}{'-'*80}{Colors.ENDC}")

def print_success(msg):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")

def print_error(msg):
    """Print error message"""
    print(f"{Colors.RED}✗ {msg}{Colors.ENDC}")

def print_info(msg):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ {msg}{Colors.ENDC}")

def validate_paths(datadir, folder, dataset_path):
    """Validate that required paths exist"""
    print_step(1, "Validating paths and parameters")
    
    errors = []
    
    # Check if datadir exists
    if not os.path.exists(datadir):
        errors.append(f"Data directory not found: {datadir}")
    else:
        print_success(f"Data directory found: {datadir}")
    
    # Check if output folder can be created
    try:
        os.makedirs(folder, exist_ok=True)
        print_success(f"Output folder ready: {folder}")
    except Exception as e:
        errors.append(f"Cannot create output folder {folder}: {e}")
    
    # Check if dataset exists
    if not os.path.exists(dataset_path):
        print_info(f"Dataset path {dataset_path} may not exist (will be created during training)")
    else:
        print_success(f"Dataset found: {dataset_path}")
    
    if errors:
        for error in errors:
            print_error(error)
        return False
    
    return True

def build_command(args_dict, script_path):
    """Build the training command"""
    print_step(2, "Building training command")
    
    cmd = ['python', '-u', script_path]
    
    for key, value in args_dict.items():
        if key != 'script':  # Skip script path
            cmd.extend([f'--{key}', str(value)])
    
    print_info("Command:")
    print(f"  {' '.join(cmd)}")
    
    return cmd

def run_training(cmd, output_dir):
    """Run training with real-time output"""
    print_step(3, "Starting training process")
    
    start_time = datetime.now()
    print_info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create log file
    log_file = os.path.join(output_dir, f"training_{start_time.strftime('%Y%m%d_%H%M%S')}.log")
    
    try:
        with open(log_file, 'w') as f:
            f.write(f"Training started at: {start_time}\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write("="*80 + "\n\n")
        
        # Run process with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        line_count = 0
        with open(log_file, 'a') as f:
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    print(f"{Colors.YELLOW}[TRAINING]{Colors.ENDC} {line}")
                    f.write(line + "\n")
                    line_count += 1
        
        return_code = process.wait()
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Write summary to log
        with open(log_file, 'a') as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Training ended at: {end_time}\n")
            f.write(f"Duration: {duration}\n")
            f.write(f"Return code: {return_code}\n")
        
        print_step(4, "Training process completed")
        
        if return_code == 0:
            print_success(f"Training completed successfully!")
            print_success(f"Output logged to: {log_file}")
            print_info(f"Total output lines: {line_count}")
            print_info(f"Duration: {duration}")
        else:
            print_error(f"Training failed with return code {return_code}")
            print_error(f"Check log file: {log_file}")
        
        return return_code
        
    except KeyboardInterrupt:
        print_error("\nTraining interrupted by user")
        process.terminate()
        return 1
    except Exception as e:
        print_error(f"Error during training: {str(e)}")
        return 1

def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Run MBA Training with Progress Tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_mba_training.py \\
    --datadir /kaggle/working/data \\
    --folder /kaggle/working/output \\
    --dataset otto \\
    --model MF

  python run_mba_training.py \\
    --datadir ./datasets \\
    --folder ./output \\
    --dataset otto \\
    --train_method pre \\
    --pretrain_early_stop_rounds 20
        """
    )
    
    # Training parameters
    parser.add_argument('--datadir', type=str, default='/kaggle/working/data',
                        help='Directory containing datasets')
    parser.add_argument('--folder', type=str, default='/kaggle/working/output',
                        help='Output directory for results')
    parser.add_argument('--dataset', type=str, default='otto',
                        help='Dataset name (otto, taobao, beibei)')
    parser.add_argument('--train_method', type=str, default='pre',
                        help='Training method (pre, normal)')
    parser.add_argument('--model', type=str, default='MF',
                        help='Model type (MF, LGN)')
    parser.add_argument('--pretrain_model', type=str, default='MF',
                        help='Pretrain model type')
    parser.add_argument('--lambda0', type=str, default='1e-4',
                        help='Regularization coefficient')
    parser.add_argument('--pretrain_early_stop_rounds', type=int, default=20,
                        help='Early stopping rounds for pretraining')
    parser.add_argument('--idx', type=int, default=0,
                        help='Index/run ID')
    parser.add_argument('--epochs', type=int, default=1000,
                        help='Number of training epochs')
    parser.add_argument('--batch_size', type=int, default=2048,
                        help='Batch size')
    parser.add_argument('--lr', type=float, default=0.001,
                        help='Learning rate')
    parser.add_argument('--emb_dim', type=int, default=32,
                        help='Embedding dimension')
    parser.add_argument('--top_k', type=int, default=20,
                        help='Top K for evaluation')
    parser.add_argument('--seed', type=int, default=2022,
                        help='Random seed')
    parser.add_argument('--script', type=str, default='MBA/main.py',
                        help='Path to MBA main script')
    
    args = parser.parse_args()
    args_dict = vars(args)
    
    # Print header
    print_header("MBA TRAINING WITH PROGRESS TRACKING")
    
    # Determine script path
    script_path = args.script
    
    # Check if running on Kaggle
    if os.path.exists('/kaggle/input/datasets/hngphongkiu/rs-mba/main.py'):
        script_path = '/kaggle/input/datasets/hngphongkiu/rs-mba/main.py'
        print_info("Running on Kaggle")
    elif not os.path.exists(script_path):
        print_error(f"Script not found: {script_path}")
        return 1
    
    # Validate paths
    dataset_path = os.path.join(args.datadir, args.dataset)
    if not validate_paths(args.datadir, args.folder, dataset_path):
        return 1
    
    # Build command
    cmd = build_command(args_dict, script_path)
    
    # Run training
    return_code = run_training(cmd, args.folder)
    
    print_header("TRAINING SESSION COMPLETE")
    return return_code

if __name__ == "__main__":
    sys.exit(main())
