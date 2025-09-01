# YAML Config Tool

Tool to visualize differences between YAML configuration files, create new configurations, and submit SLURM jobs.

### Use

1. Place `app.py`, `templates/index.html`, and `config.json` in your project directory
2. Edit `config.json` to match your paths and settings
3. Run `python app.py`
4. Open http://localhost:5000 or as specicified in config

## Configuration

The tool is configured via `config.json`:

### App Settings
```json
{
  "app": {
    "host": "0.0.0.0",     // Server host
    "port": 5000,          // Server port
    "debug": true          // Debug mode
  }
}
```

### Paths
```json
{
  "paths": {
    "configs_directory": "/path/to/configs",     // Directory containing YAML files
    "working_directory": "/path/to/work",        // Working directory for tool
    "slurm_template_file": "/path/to/run.sh"     // SLURM template file (optional)
  }
}
```

### SLURM Settings
```json
{
  "slurm": {
    "default_partition": "general",
    "default_time": "02:00:00",
    "default_nodes": 1,
    "default_cpus_per_task": 4,
    "default_mem": "8G",
    "default_job_name": "yamltool_job",
    "ssh_host": "daic",                          // SSH hostname for cluster
    "ssh_user": "username",
    "output_pattern": "slurm-%j.out",
    "error_pattern": "slurm-%j.err"
  }
}
```

### File Watching
```json
{
  "file_watching": {
    "enabled": true,                             // Enable automatic file watching
    "recursive": true,                           // Watch subdirectories
    "patterns": ["*.yaml", "*.yml"]              // File patterns to watch
  }
}
```

## SLURM Template

If you provide a `slurm_template_file` in your configuration, the tool will use it as a template for job submissions. The template can include placeholders:

- `{job_name}` - Job name
- `{memory}` - Memory allocation
- `{config_path}` - Path to config file
- `{gpu_line}` - GPU allocation line (if GPU requested)
- `{partition}` - SLURM partition
- `{time}` - Time limit
- `{nodes}` - Number of nodes
- `{output_pattern}` - Output file pattern
- `{error_pattern}` - Error file pattern

Example template:
```bash
#!/bin/sh
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --time={time}
#SBATCH --nodes={nodes}
#SBATCH --mem={memory}
{gpu_line}
#SBATCH --output={output_pattern}
#SBATCH --error={error_pattern}

## Dependencies

using python 3.10

```bash
pip install flask pyyaml watchdog
```
