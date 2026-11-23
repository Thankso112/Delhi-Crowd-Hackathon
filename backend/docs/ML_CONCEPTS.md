# ML concepts used in this project

One or two sentences each, with a real-world example. The same list is served by the API at `/api/ml/insights`.

- **Train / test split** - Hide part of the data while the model learns, then score it on the hidden part, so we test understanding and not memory. *Example: A student practises on past papers and is judged on a new paper.*
- **Temporal split** - Train on the past and test on the future, never the other way round, so no future information leaks into training. *Example: Predict next week's bus crowding from the previous three weeks only.*
- **Feature scaling (StandardScaler)** - Rescale every column to a similar range so no column dominates only because its numbers are bigger. *Example: Distance in km and hour of day are put on the same scale before KNN measures 'closeness'.*
- **Winsorizing** - Cut extreme values back to the 1st and 99th percentile of the training data so a few huge numbers cannot distort the model. *Example: One day with a ticket-system glitch is capped instead of ruining the average.*
- **Linear Regression (OLS)** - Fits the best straight line (a weighted sum of features) through the data to predict a number. *Example: Predicting house price from size, bedrooms and age.*
- **Ridge and Lasso (regularisation)** - Linear regression with a brake: Ridge shrinks all weights, Lasso can shrink some to exactly zero, which also selects features. *Example: A teacher who stops you explaining a result with too many reasons.*
- **Elastic Net** - A mix of Ridge and Lasso, useful when several features overlap. *Example: Latitude, longitude and distance to the centre all describe 'where', so their weights are shared sensibly.*
- **KNN (K-Nearest Neighbours)** - To predict a new case, look at the K most similar known cases and let them vote (or average them). *Example: Judging a restaurant by the ratings of the 10 most similar ones nearby.*
- **SVM (Support Vector Machine)** - Draws the boundary between classes with the widest possible safety margin; with a kernel the boundary can curve. *Example: Separating spam from normal mail with the cleanest dividing line.*
- **Decision Tree** - A flow-chart of yes/no questions that ends in an answer; easy to read but can memorise noise if too deep. *Example: A doctor's triage chart.*
- **Random Forest** - Many different trees vote and their answers are averaged, which is steadier than any single tree. *Example: Asking 200 people to guess the sweets in a jar and taking the average.*
- **Gradient Boosting** - Builds trees one after another, each fixing the mistakes of the previous ones. *Example: A student who redoes only the questions they got wrong, round after round.*
- **Logistic Regression** - A linear model that outputs the probability of each class instead of a number. *Example: A bank estimating the chance a loan will be repaid.*
- **Naive Bayes** - Classifies using probabilities and pretends the features are independent, which makes it very fast. *Example: Spam filters multiply the probabilities of the words in a mail.*
- **K-Means clustering** - With no labels, groups similar items by repeatedly moving K group centres to the middle of their members. *Example: Grouping bus routes into 'morning commuter' and 'all-day' types.*
- **PCA (Principal Component Analysis)** - Squeezes many columns into a few new ones that keep most of the information, so data can be drawn on a 2-D plot. *Example: Plotting routes described by six numbers on a single flat map.*
- **Cross-validation** - Repeats the train/test experiment several times on different hidden parts and averages the scores, so one lucky split cannot fool us. *Example: Five mock exams instead of one.*
- **GridSearchCV (hyper-parameter tuning)** - Tries every combination of a model's settings with cross-validation and keeps the best. *Example: Trying several oven temperatures and times to find the best cake.*
- **Overfitting** - The model memorises the training data and does worse on new data; shown by a big gap between train and test scores. *Example: Learning last year's answers by heart instead of the subject.*
- **MAE, RMSE and R2** - MAE is the average size of the error, RMSE punishes big errors more, R2 is the share of variation explained (1 perfect, 0 no better than the average). *Example: An exam score shows how far off you were on average.*
- **Accuracy, macro-F1 and confusion matrix** - Accuracy is the share of correct labels; macro-F1 treats every class equally, even rare ones; the confusion matrix shows which classes get mixed up. *Example: A spam filter that is 95% accurate but never catches a rare scam would score poorly on macro-F1.*
