#!/usr/bin/env python3
import csv
import matplotlib.pyplot as plt
import numpy as np

# Read the CSV file and extract prep times
prep_times = []
with open('test.csv', 'r') as file:
    reader = csv.reader(file)
    header = next(reader)  # Skip header
    for row in reader:
        if len(row) >= 5:  # Make sure we have enough columns
            prep_times.append(int(row[4]))  # Column 4 is prep time

# Create histogram
plt.figure(figsize=(12, 8))
n, bins, patches = plt.hist(prep_times, bins=8, edgecolor='black', alpha=0.7, color='skyblue')

# Customize the plot
plt.title('Distribution of Recipe Prep Times', fontsize=16, fontweight='bold')
plt.xlabel('Prep Time (minutes)', fontsize=12)
plt.ylabel('Number of Recipes', fontsize=12)
plt.grid(axis='y', alpha=0.3)

# Add statistics lines
mean_time = np.mean(prep_times)
median_time = np.median(prep_times)
plt.axvline(mean_time, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_time:.1f} min')
plt.axvline(median_time, color='orange', linestyle='--', linewidth=2, label=f'Median: {median_time:.1f} min')

# Add value labels on bars
for i, v in enumerate(n):
    if v > 0:
        plt.text(bins[i] + (bins[i+1] - bins[i])/2, v + 0.1, str(int(v)), 
                ha='center', va='bottom', fontsize=10)

plt.legend()
plt.tight_layout()

# Save the plot
plt.savefig('prep_time_histogram.png', dpi=300, bbox_inches='tight')
plt.savefig('prep_time_histogram.pdf', bbox_inches='tight')

print(f"Histogram created successfully!")
print(f"Prep time statistics:")
print(f"- Mean: {mean_time:.2f} minutes")
print(f"- Median: {median_time:.2f} minutes")
print(f"- Min: {min(prep_times)} minutes")
print(f"- Max: {max(prep_times)} minutes")
print(f"- Standard deviation: {np.std(prep_times):.2f} minutes")
print(f"- Total recipes: {len(prep_times)}")

# Show bin ranges and counts
print(f"\nHistogram bins:")
for i in range(len(bins)-1):
    count = int(n[i]) if i < len(n) else 0
    if count > 0:
        print(f"- {bins[i]:.0f}-{bins[i+1]:.0f} minutes: {count} recipes")

print(f"\nFiles created:")
print(f"- prep_time_histogram.png")
print(f"- prep_time_histogram.pdf")