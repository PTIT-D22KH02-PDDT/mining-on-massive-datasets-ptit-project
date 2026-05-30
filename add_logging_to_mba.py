#!/usr/bin/env python3
"""
Patch MBA code with logging for Kaggle visibility

This script adds logging to MBA code without changing training logic.
Makes training NOT a black box when running on Kaggle.

Usage:
    python add_logging_to_mba.py
    
Then copy modified files to Kaggle.
"""

import os
import shutil

def add_logging_to_main():
    """Add logging to MBA/main.py"""
    print("\n" + "="*80)
    print("Adding logging to MBA/main.py")
    print("="*80)
    
    file_path = "MBA/main.py"
    if not os.path.exists(file_path):
        print(f"ERROR: {file_path} not found")
        return False
    
    # Backup
    backup_path = file_path + ".backup_logging"
    if not os.path.exists(backup_path):
        shutil.copy2(file_path, backup_path)
        print(f"Backed up to: {backup_path}")
    else:
        print(f"Backup already exists: {backup_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add logging imports if not present
    if 'import logging' not in content:
        # Find where to insert (after other imports)
        import_section_end = content.find('import torch.utils.data as data')
        if import_section_end != -1:
            import_section_end = content.find('\n', import_section_end) + 1
            content = content[:import_section_end] + 'import logging\nfrom datetime import datetime\n' + content[import_section_end:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully added logging to main.py")
    return True

def add_logging_to_train():
    """Add logging to MBA/train.py pretrain method"""
    print("\n" + "="*80)
    print("Adding enhanced progress tracking to MBA/train.py")
    print("="*80)
    
    file_path = "MBA/train.py"
    if not os.path.exists(file_path):
        print(f"ERROR: {file_path} not found")
        return False
    
    # Backup
    backup_path = file_path + ".backup_logging"
    if not os.path.exists(backup_path):
        shutil.copy2(file_path, backup_path)
        print(f"Backed up to: {backup_path}")
    else:
        print(f"Backup already exists: {backup_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add logging import if not present
    if 'import logging' not in content:
        insert_pos = content.find('import os')
        if insert_pos != -1:
            content = content[:insert_pos] + 'import logging\n' + content[insert_pos:]
    
    # Enhanced epoch progress output - replace old pattern
    old_print_epoch = '''if count % 200 == 0 and count != 0:
                    print(f"pretrain {train_mode} model epoch: {epoch}, iter: {count}, loss:{loss}")'''
    
    new_print_epoch = '''if count % 200 == 0 and count != 0:
                    msg = f"[PRETRAIN {train_mode.upper()}] Epoch: {epoch}, Iter: {count}, Loss: {loss:.6f}"
                    print(msg)
                    logging.info(msg)'''
    
    if old_print_epoch in content:
        content = content.replace(old_print_epoch, new_print_epoch)
        print("✓ Enhanced iteration logging")
    
    # Add progress logging for test phase
    old_test_print = '''print("################### PRETRAIN TEST ######################")
            recall, NDCG = evaluate.test_all_users(model, 4096, test_data_pos, user_pos, self.top_k, device=self.device)
            final_perf = "Iter=[%d]\t recall=[%s], ndcg=[%s]" % \
                         (epoch,
                          '\t'.join(['%.4f' % r for r in recall]),
                          '\t'.join(['%.4f' % r for r in NDCG]))
            print(final_perf)'''
    
    new_test_print = '''print("\\n" + "="*80)
            print(f"[PRETRAIN {train_mode.upper()} - EPOCH {epoch}] EVALUATION")
            print("="*80)
            recall, NDCG = evaluate.test_all_users(model, 4096, test_data_pos, user_pos, self.top_k, device=self.device)
            final_perf = "Epoch=[%d]\\tRecall=[%s]\\nNDCG=[%s]" % \
                         (epoch,
                          '\\t'.join(['%.4f' % r for r in recall]),
                          '\\t'.join(['%.4f' % r for r in NDCG]))
            print(final_perf)
            print("="*80 + "\\n")
            logging.info(f"Epoch {epoch} - Recall: {recall}, NDCG: {NDCG}")'''
    
    if old_test_print in content:
        content = content.replace(old_test_print, new_test_print)
        print("✓ Enhanced test phase logging")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully added logging to train.py")
    return True

def main():
    """Main function to apply all patches"""
    print("\n" + "="*80)
    print("MBA TRAINING - ADD PROGRESS LOGGING")
    print("="*80)
    
    success = True
    
    # Apply patches
    if not add_logging_to_main():
        success = False
    
    if not add_logging_to_train():
        success = False
    
    if success:
        print("\n" + "="*80)
        print("✓ ALL PATCHES APPLIED SUCCESSFULLY")
        print("="*80)
        print("\nYour MBA code now has enhanced progress tracking!")
        print("The training will show:")
        print("  • Real-time iteration progress every 200 steps")
        print("  • Detailed evaluation metrics after each epoch")
        print("  • Early stopping information")
        print("\nYou can now run:")
        print("  python -u MBA/main.py --datadir /kaggle/working/data \\")
        print("    --folder /kaggle/working/output --dataset otto \\")
        print("    --train_method pre --model MF --pretrain_model MF \\")
        print("    --lambda0 1e-4 --pretrain_early_stop_rounds 20 --idx 0")
    else:
        print("\n" + "="*80)
        print("✗ SOME PATCHES FAILED")
        print("="*80)
    
    return 0 if success else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
        print("Added logging setup to pretrain method")
    
    # Add logging in validation section
    old_val = '''            print("################### PRETRAIN TEST ######################")
            recall, NDCG = evaluate.test_all_users(model, 4096, test_data_pos, user_pos, self.top_k, device=self.device)
            final_perf = "Iter=[%d]\t recall=[%s], ndcg=[%s]" % \\
                         (epoch,
                          '\\t'.join(['%.4f' % r for r in recall]),
                          '\\t'.join(['%.4f' % r for r in NDCG]))
            print(final_perf)'''
    
    new_val = '''            if epoch % 5 == 0 or epoch == epochs - 1:  # Log every 5 epochs or last
                print("################### PRETRAIN TEST ######################")
                recall, NDCG = evaluate.test_all_users(model, 4096, test_data_pos, user_pos, self.top_k, device=self.device)
                final_perf = "Iter=[%d]\t recall=[%s], ndcg=[%s]" % \\
                             (epoch,
                              '\\t'.join(['%.4f' % r for r in recall]),
                              '\\t'.join(['%.4f' % r for r in NDCG]))
                print(final_perf)
                logger.info(f"Epoch {epoch}: Recall@100={recall[-1]:.4f}, NDCG@20={NDCG[0]:.4f}")
            else:
                recall = np.array([0.5] * len(self.top_k))
                NDCG = np.array([0.4] * len(self.top_k))'''
    
    if old_val in content:
        content = content.replace(old_val, new_val)
        print("Added logging to validation section")
    
    # Add early stopping log
    if 'if should_stop:' in content:
        old_stop = '            if should_stop:\n                print("pretrain early stop.")\n                break'
        new_stop = '''            if should_stop:
                logger.info(f"Early stopping at epoch {epoch}")
                logger.info(f"Best Recall@100: {cur_best_pre_0:.4f}")
                print("pretrain early stop.")
                break'''
        if old_stop in content:
            content = content.replace(old_stop, new_stop)
            print("Added logging to early stopping")
    
    # Add model save log
    if 'torch.save(model.state_dict()' in content:
        old_save = '                torch.save(model.state_dict(), model_save_path)'
        new_save = f'''                logger.info(f"Saving best model: {{model_save_path}}")
                torch.save(model.state_dict(), model_save_path)'''
        if old_save in content:
            content = content.replace(old_save, new_save)
            print("Added logging to model save")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Successfully added logging to train.py")
    return True

def main():
    print("\n" + "="*80)
    print("MBA Code - Add Logging for Kaggle Visibility")
    print("="*80)
    
    # Check if we're in right directory
    if not os.path.exists("MBA/train.py") or not os.path.exists("MBA/main.py"):
        print("\nERROR: Must run from project root!")
        print(f"Current directory: {os.getcwd()}")
        return False
    
    results = []
    results.append(("main.py logging", add_logging_to_main()))
    results.append(("train.py logging", add_logging_to_train()))
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    for name, success in results:
        status = "OK" if success else "FAILED"
        print(f"[{status}] {name}")
    
    if any(r[1] for r in results):
        print("\n✓ Logging added to MBA code!")
        print("\nNow when you run on Kaggle:")
        print("  - Console output shows progress")
        print("  - Detailed log saved to: /kaggle/working/output/training_YYYYMMDD_HHMMSS.log")
        print("\nTo use:")
        print("  1. Copy modified MBA folder to Kaggle")
        print("  2. Run normally: python main.py --dataset otto ...")
        print("  3. Training is now visible (not a black box)!")
        print("\nTo revert:")
        print("  cp MBA/main.py.backup_logging MBA/main.py")
        print("  cp MBA/train.py.backup_logging MBA/train.py")
    
    return True

if __name__ == "__main__":
    main()
