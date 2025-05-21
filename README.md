# Gradescope Regrade Request Analytics

The `analyze.py` script is a helpful utility to analyze regrade requests for a given assignment on Gradescope.

## Installation

To install most of the dependencies, run `pip install -r requirements.txt`.

This script requires the isntallation of PyTorch and/or TensorFlow as well, in order to classify regrade request responses. Since this installation process is involved, it is not specified in the requirements file—see [https://www.tensorflow.org/install/](https://www.tensorflow.org/install/) or [https://pytorch.org/](https://pytorch.org/) for full installation instructions.

PyTorch/TensorFlow does not need to be installed if classification is not desired; pass `--no-classify` to avoid the import.

## Usage

See `python3 analyze.py -h` for full help information.

To run the analyze script interactively, run `python3 analyze.py [arguments]`. The script will ensure that you are logged into Gradescope, and then prompts for a URL to the Gradescope regrade requests page for an assignment. Without any additional arguments, the script will fetch all regrade requests, and immediately exit without printing anything else (the regrade request info will be cached for future runs).

The script takes the following arguments:

- `--url URL`: Provides a Gradescope regrade request URL to the script, disabling the prompt.
- `--cookies LOCATION`: Cache location for saved cookies.
- `--parallel PARALLEL` (alias: `-p PARALLEL`): Number of processes to use for parallel requests during regrade request fetching.
- `--no-classify`: Disable regrade request acceptance classification.
- `--cache LOCATION`: Cache location for saved regrade request information.
- `--refresh-cache`: Force refresh the cache for the given regrade request link.
- `--min-requests MIN_REQUESTS`: Minimum number of regrade requests for a student in order to display the regrade request details (only applies to `--print-requests` and `--print-student-stats`).
- `--metric [unique | total]`: Specifies the metric used for the regrade request statistics display; `unique` uses the number of unique questions that were requested, and `total` uses the total number of comments submitted.

Display options:

- `--print-requests`: Print all regrade request details, in a tabular format.
- `--print-student-stats`: Print regrade request statistics for each student.
- `--print-staff-stats`: Print regrade request statistics for each staff member.
- `--plot-student-stats`: Plot student regrade request statistics.

## Classification

The script will automatically take chains of regrade requests (i.e. student requests and staff responses) and classify whether the chain of requests and responses corresponds to an accepted or rejected regrade request. Since Gradescope does not actually store this information, we use a language model to perform this classification.

In particular, we use the `roberta-large-mnli` model from the `transformers` library from HuggingFace to perform zero-shot classification. See the `classify_responses` function in `analyze.py` for additional implementation and prompt details.

Since this model can take a while to run, it is best to run the model on a GPU; if no GPU is found, the CPU is used as a fallback, but this can be prohibitively slow. To disable regrade request classification, pass `--no-classify` as a CLI argument. Note that without classification, many regrade request analytics will not be computed.
