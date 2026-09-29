args <- commandArgs(trailingOnly = TRUE)
data <- read.csv(args[1])
set.seed(20260929)
scores <- rowMeans(data)
result <- replicate(5000, mean(sample(scores, length(scores), replace = TRUE)))
write.csv(data.frame(metric = c("mean", "ci_low", "ci_high"),
                     value = c(mean(scores), quantile(result, 0.025), quantile(result, 0.975))),
          args[2], row.names = FALSE)
