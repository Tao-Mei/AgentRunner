args <- commandArgs(trailingOnly = TRUE)
if (!requireNamespace("lavaan", quietly = TRUE)) stop("lavaan is required")
data <- read.csv(args[1])
model <- "factor =~ item1 + item2 + item3 + item4 + item5 + item6"
fit <- lavaan::cfa(model, data = data)
if (!lavaan::lavInspect(fit, "converged")) stop("CFA did not converge")
measures <- lavaan::fitMeasures(fit, c("cfi", "rmsea", "srmr"))
write.csv(data.frame(metric = names(measures), value = as.numeric(measures)), args[2], row.names = FALSE)
